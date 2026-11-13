"""Trusted launcher for workspace commands on Linux."""
import ctypes as C
import json
import errno
import os
from pathlib import Path
import platform
import resource
import struct
import sys

EXECUTE = 1 << 0
WRITE_FILE = 1 << 1
READ_FILE = 1 << 2
READ_DIR = 1 << 3
MAKE_DIR = 1 << 7
MAKE_REG = 1 << 8
TRUNCATE = 1 << 14
READ_TREE = READ_FILE | READ_DIR | EXECUTE
WRITE_TREE = WRITE_FILE | MAKE_DIR | MAKE_REG | TRUNCATE | (1 << 4) | (1 << 5) | (1 << 13)


def checked(value):
    if value < 0:
        error = C.get_errno()
        raise OSError(error, os.strerror(error))
    return value


def restrict_files(writable, helper):
    if platform.machine() not in {"x86_64", "aarch64"}:
        raise RuntimeError("unsupported Linux architecture for Landlock")
    libc = C.CDLL(None, use_errno=True)
    create, add, restrict = 444, 445, 446
    abi = checked(libc.syscall(create, C.c_void_p(), 0, 1))
    if abi < 3:
        raise RuntimeError("Landlock ABI 3 or newer is required")
    # Handle the filesystem rights through TRUNCATE, and device ioctls on ABI 5+.
    handled = C.c_uint64((1 << (16 if abi >= 5 else 15)) - 1)
    ruleset = checked(libc.syscall(create, C.byref(handled), C.sizeof(handled), 0))
    try:
        def allow(path, rights):
            if not path.exists():
                return
            fd = os.open(path, os.O_PATH | os.O_CLOEXEC)
            try:
                rule = C.create_string_buffer(struct.pack("=Qi", rights, fd))
                checked(libc.syscall(add, ruleset, 1, C.byref(rule), 0))
            finally:
                os.close(fd)

        version = f"{sys.version_info.major}.{sys.version_info.minor}"
        lib_dir = Path(sys.base_prefix) / "lib"
        for folder in ("/usr/bin", "/usr/lib", "/usr/lib64", "/lib", "/lib64",
                       "/usr/local/bin", str(lib_dir / f"python{version}")):
            path = Path(folder).resolve()
            if path != Path("/"):
                allow(path, READ_TREE)
        for root in json.loads(os.environ.get("HARNESS_LIBRARY_ROOTS", "[]")):
            allow(Path(root).resolve(), READ_TREE)
        allow(Path(__file__).with_name("_python_runner.py").resolve(), READ_FILE)
        allow(Path(sys.executable).resolve(), EXECUTE | READ_FILE)
        for library in lib_dir.glob(f"libpython{version}*.so*"):
            allow(library.resolve(), EXECUTE | READ_FILE)
        allow(Path("/etc/ld.so.cache"), READ_FILE)
        allow(Path("/dev/null"), READ_FILE | WRITE_FILE)
        allow(Path("/dev/urandom"), READ_FILE)
        allow(Path.cwd(), READ_TREE | (WRITE_TREE if writable else 0))
        allow(Path(os.environ["TMPDIR"]), READ_TREE | WRITE_TREE)
        if helper:
            allow(Path(helper), READ_FILE)
        checked(libc.prctl(38, 1, 0, 0, 0))  # PR_SET_NO_NEW_PRIVS
        checked(libc.syscall(restrict, ruleset, 0))
    finally:
        os.close(ruleset)


def restrict_syscalls(seccomp):
    seccomp.seccomp_init.argtypes = [C.c_uint32]
    seccomp.seccomp_init.restype = C.c_void_p
    seccomp.seccomp_syscall_resolve_name.argtypes = [C.c_char_p]
    seccomp.seccomp_rule_add.argtypes = [C.c_void_p, C.c_uint32, C.c_int, C.c_uint]
    seccomp.seccomp_load.argtypes = [C.c_void_p]
    seccomp.seccomp_release.argtypes = [C.c_void_p]
    policy = seccomp.seccomp_init(0x7FFF0000)  # SCMP_ACT_ALLOW
    if not policy:
        raise RuntimeError("cannot initialize seccomp")
    try:
        # No inherited sockets. Block new sockets and alternate paths to external
        # processes, mounts and filesystem handles. Keep subprocesses in the
        # worker's process group so the parent can stop them together.
        denied = """
            socket socketpair socketcall connect bind listen accept accept4
            sendto sendmsg sendmmsg recvfrom recvmsg recvmmsg
            io_uring_setup io_uring_enter io_uring_register
            ptrace process_vm_readv process_vm_writev pidfd_getfd pidfd_send_signal
            kill tkill tgkill rt_sigqueueinfo rt_tgsigqueueinfo
            setsid setpgid unshare setns mount umount2 pivot_root chroot
            move_mount fsopen fsconfig fsmount open_tree mount_setattr
            open_by_handle_at bpf userfaultfd perf_event_open
            keyctl add_key request_key shmget shmat semget msgget mq_open
            chmod fchmod fchmodat fchmodat2 chown fchown fchownat lchown
            setxattr fsetxattr lsetxattr removexattr fremovexattr lremovexattr
        """
        for name in denied.split():
            number = seccomp.seccomp_syscall_resolve_name(name.encode("ascii"))
            if number != -1 and seccomp.seccomp_rule_add(policy, 0x00050000 | errno.EPERM, number, 0) != 0:
                raise RuntimeError(f"cannot block syscall {name}")
        # prlimit64(pid != 0) can modify sibling processes despite Landlock.
        # Preserve self queries/limits via pid 0, needed by the Python runtime.
        class Comparison(C.Structure):
            _fields_ = [("arg", C.c_uint), ("op", C.c_int),
                        ("datum_a", C.c_uint64), ("datum_b", C.c_uint64)]
        seccomp.seccomp_rule_add_array.argtypes = [C.c_void_p, C.c_uint32, C.c_int,
                                                   C.c_uint, C.POINTER(Comparison)]
        number = seccomp.seccomp_syscall_resolve_name(b"prlimit64")
        condition = Comparison(0, 1, 0, 0)  # SCMP_CMP_NE, argument 0 != 0
        if number != -1 and seccomp.seccomp_rule_add_array(policy, 0x00050000 | errno.EPERM,
                                                          number, 1, C.byref(condition)) != 0:
            raise RuntimeError("cannot restrict prlimit64 to self")
        if seccomp.seccomp_load(policy) != 0:
            raise RuntimeError("cannot apply seccomp")
    finally:
        seccomp.seccomp_release(policy)


def main():
    writable, helper, cpu, *command = sys.argv[1:]
    cpu = int(cpu)
    # Before Landlock: OOM killer must pick this child, not the harness.
    try:
        with open("/proc/self/oom_score_adj", "w") as f:
            f.write("1000")
    except OSError:
        pass
    try:
        seccomp = C.CDLL("libseccomp.so.2")
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu + 1))
        resource.setrlimit(resource.RLIMIT_AS, (2 * 1024**3,) * 2)
        resource.setrlimit(resource.RLIMIT_FSIZE, (8 * 1024**2,) * 2)
        restrict_files(writable == "write", helper)
        restrict_syscalls(seccomp)
        os.execv(command[0], command)
    except (OSError, ValueError, RuntimeError) as error:
        sys.stderr.write(f"isolation unavailable: {error}\n")
        return 125


if __name__ == "__main__":
    sys.exit(main())
