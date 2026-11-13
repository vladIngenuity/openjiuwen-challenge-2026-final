# Техническая документация проекта

Этот комплект описывает исходный код ветки `astra-night-review-20261113` после
коммита с endgame-перепроверкой. Исторический `README.md` описывает также
старую стратегию `baseline`; для текущего кандидата используйте
`--strategy empirical_hybrid`.

Документы:

- [Архитектура и потоки данных](ARCHITECTURE.md)
- [Каждая функция и метод проекта](FUNCTIONS.md)
- [Контейнер, восемь CPU и проверка запуска](CONTAINER.md)
- [Контракт Strategy/Executor](../contracts/strategy.md)
- [Измерения маршрутизации моделей](../research/empirical_hybrid_20261113.md)

Документация охватывает рабочий код `run_agent.py`, `harness/` и `tools/`.
Тесты служат проверкой поведения, а `samples/` — публичными фикстурами.
Локальные `benchmark320/`, `experiments/` и закрытые эталоны не входят в образ.

Для обновления справочника функций после правок:

```bash
python tools/document_api.py
python tools/document_api.py --check
```
