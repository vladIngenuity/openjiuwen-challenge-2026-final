# Контейнер и запуск на восьми логических CPU

## Поддерживаемая аппаратная среда

Заявлены два Intel Xeon E5-2696 v4, x86-64, Broadwell, с AVX2/AES. Образу
нужна архитектура `linux/amd64`; количество сокетов и частота не зашиваются
в образ. В таблице регламента сказано «не более 4 ядра», но точная команда
организаторов использует `--cpus 8`. Заявленное команде ограничение — восемь
логических CPU. Вспомогательный скрипт задаёт и квоту (`--cpus=8`), и восемь
разрешённых ID (`--cpuset-cpus`). Команда организаторов задаёт только квоту,
поэтому привязка к восьми ID на их хосте не гарантирована. `CPUSET` определяют
по реальному хосту; `0,1,2,3,4,5,6,7` — только пример, не универсальный ID.
Семантика флагов сверена с [документацией Docker по ограничениям CPU](https://docs.docker.com/engine/containers/resource_constraints/).

## Сборка

```bash
cd /home/vladislav/Documents/projects/openjiuwen-challenge/openjiuwen-ml
docker build --platform linux/amd64 -t hack:latest -f Dockerfile .
```

Образ содержит Python 3.12.8, `openjiuwen==0.1.19`, ограничения транзитивных
версий из `constraints.txt`, `libseccomp2`, исходник harness и публичные
`samples/`. Build-time selfcheck проверяет создание SDK без LLM-сети.
`.dockerignore` формирует закрытый allowlist контекста: экспериментальные
логи, локальные архивы, скрытые эталоны, ключи и `.git` не отправляются в
Docker daemon. Тег `hack:latest` локальный; digest определяется после сборки.

## Проверка образа без API

```bash
docker run --rm --platform linux/amd64 --network none \
  --cpuset-cpus 0,1,2,3,4,5,6,7 --cpus=8 --memory=16g \
  --user "$(id -u):$(id -g)" --read-only \
  --tmpfs /tmp:rw,nosuid,nodev,size=2g --cap-drop ALL \
  --pids-limit 512 --security-opt no-new-privileges \
  --entrypoint python hack:latest /app/tools/selfcheck.py
```

Замените пример CPU ID на доступные восемь. Этот тест запускает восемь
публичных примеров без API-ключа. При отсутствии Landlock/seccomp режим
`auto` может деградировать; это видно в stderr и не эквивалентно полной
изоляции. Не ослабляйте защиту хоста для получения зелёного selfcheck.

## Конкурсный запуск

Каталог задач должен быть чистой копией, доступной на запись UID оператора.
Ответы появляются внутри него. Для прокси нужен разрешённый контейнеру
маршрут сети; `CONTAINER_NETWORK=hack-net` по умолчанию, как в регламенте.
Ключ передаётся только переменной окружения.

```bash
export TASKS_DIR=/absolute/path/to/tasks
export CPUSET=0,1,2,3,4,5,6,7
export LLM_BASE_URL=https://proxy.example/v1
read -rs -p 'LLM_API_KEY: ' LLM_API_KEY; echo; export LLM_API_KEY
export BUDGET=100000
export HARNESS_TIME_LIMIT=3300
export HARNESS_REASONING_USAGE=included  # уточнить по контракту usage прокси
bash tools/run_container.sh
```

Скрипт ставит `--cpuset-cpus`, `--cpus=8`, `--memory=16g`, read-only rootfs, tmpfs `/tmp`,
непривилегированный UID/GID, `--cap-drop ALL`, `no-new-privileges`, лимит
процессов 512 и монтирует только каталог задач. Стратегия по умолчанию в
этом скрипте `empirical_hybrid`; образ задаёт `HARNESS_STRATEGY=empirical_hybrid`,
поэтому штатная команда организаторов выбирает эту стратегию без параметра.
Локальный Python вне образа без переменной окружения использует `baseline`.
`--out /data/tasks/results.json` можно
передать скрипту аргументом. Трассу и журнал включайте лишь с путями внутри
смонтированного каталога задач.

Проверка ограничений после запуска: `docker inspect <container>` →
`HostConfig.NanoCpus=8000000000` и восемь ID в `HostConfig.CpusetCpus`;
`docker exec <container> sh -c 'cat /proc/self/status | grep Cpus_allowed_list'`.
Кратковременный запуск может завершиться до inspect; для приёмки используйте
отдельный тестовый контейнер с теми же флагами. `nproc` может показывать квоту
или cpuset в зависимости от libc и ядра, поэтому не заменяет inspect.

## Сверка с регламентом

Регламент требует сборку `docker build -t hack:latest` до 1000 секунд,
репозиторий меньше 100 МБ без `.git`, образ меньше 4 ГБ, один час на решение,
память не более 16 ГБ. Штатный запуск использует сеть `hack-net`, переменные
`LLM_BASE_URL` и `LLM_API_KEY`, записываемый `/data/tasks`, read-only rootfs,
tmpfs `/tmp` на 2 ГБ, `--cap-drop ALL`, `no-new-privileges`, `--cpus 8`,
`--memory 16g`, `--pids-limit 512`, `/app/run_agent.py --tasks-dir /data/tasks`.
CI повторяет существенные флаги и проверяет созданный `answer.txt`, но
использует `--cpus 2`: GitHub runner предоставляет только два CPU и отвергает
квоту 8. Конкурсный скрипт и опубликованная команда организаторов используют 8.
Регламент упоминает переменную `OUT`, но не передаёт её в опубликованной
команде Docker; запись решения не зависит от `OUT`. Монтирование `:rw` само
по себе не предоставляет права записи в каталоги задач: при `--cap-drop ALL`
root контейнера не смог создать `answer.txt` в каталогах хост-пользователя с
правами `755`. Организаторы должны предоставить записываемые каталоги задач
(например, подходящие UID/GID, ACL или права). В CI тестовая копия получает
`a+rwX`; это проверяет контейнер только при выполнении этого предусловия.

Ссылку на GitHub/GitFlic следует отправить на `openjiuwen_org@nsu.ru` не
позднее 13 ноября 2026 года по московскому времени, указав команду
«Индийская техподдержка» в теме или тексте. Для приватного репозитория
`promsoft` и `madrugado` должны иметь доступ на момент закрытия конкурса.
Оценивается последний коммит к этому моменту; открытый PR сам по себе не
переносит код в основную ветку.

## Что подтверждено и что ещё требует проверки

Локально проверены shell-синтаксис, каталог функций и Python selfcheck (8/8).
На текущей машине отсутствуют Docker/Podman CLI и daemon socket. Образ
`linux/amd64` собран в [GitHub Actions run 43471047086](https://github.com/ArciomKapitonau/openjiuwen-harness/actions/runs/43471047086)
из коммита `a70bc6e`; контейнерный offline selfcheck и сохранение образа
прошли. Артефакт `hack-linux-amd64` имеет размер 241146945 байт и срок
хранения до 20 ноября 2026 года. Его SHA-256 `d449b30218f3b0f584a21a448a45db4ff663bb46bf9772f046f898ace12cd5bf`
относится к GitHub artifact, а не к Docker image ID. Реальный запуск на
восьми логических CPU и подключение к конкурсному прокси ещё не проверены.
Новый коммит и повторная сборка проверяются в GitHub Actions; локальный
Docker недоступен. Доступ жюри к приватному репозиторию проверяется отдельно.

Для PR добавлен workflow `.github/workflows/container-build.yml`: он строит
`linux/amd64`, запускает публичный offline selfcheck и сохраняет полный образ
архивом `hack-linux-amd64.tar.gz` на семь дней. GitHub runner не подтверждает
доступность восьми логических CPU у организаторов; квоту и cpuset нужно
проверить на целевой машине. После скачивания архива: `docker load -i
hack-linux-amd64.tar.gz`.
