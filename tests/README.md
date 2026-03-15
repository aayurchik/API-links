### Юнит-тесты

```bash
pytest tests/unit_tests.py -v

### Функциональные тесты

```bash
pytest tests/functional_test.py -v

### Все тесты с измерением покрытия

```bash
coverage run --source=src -m pytest tests/unit_tests.py tests/functional_test.py
coverage report
coverage html  # генерирует отчёт в папку htmlcov/

### Нагрузочное тестирование Locust

# Создание популярных ссылок 
```bash
0..9 | ForEach-Object { $i = $_ + 100; Invoke-RestMethod -Uri "http://localhost:8000/links/shorten" -Method Post -Headers @{"Content-Type"="application/json"} -Body (@{original_url="https://example.com/$i"; custom_alias="load$i"} | ConvertTo-Json) }

# Запуск Locust
```bash
locust -f tests/load_test.py --host=http://localhost:8000

### Покрытие кода
Полный HTML-отчёт покрытия доступен в папке [`htmlcov/index.html`](../htmlcov/index.html) – скачайте и откройте в браузере.

### Нагрузочное тестирование
100 одновременных пользователей, spawn rate 10/сек, длительность ~5 мин. Сценарии: 60% редиректы по популярным ссылкам, 30% создание новых ссылок, 10% запрос статистики.

Графики Locust
https://images/statistics.png
Рисунок 1. Статистика запросов (таблица)

https://images/links.png
Рисунок 2. Графики времени ответа и RPS