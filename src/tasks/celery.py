# from celery import Celery
# from src.config import REDIS_HOST, REDIS_PORT
# from celery.schedules import crontab


# celery = Celery(
#     'tasks',
#     broker=f'redis://{REDIS_HOST}:{REDIS_PORT}/0',
#     backend=f'redis://{REDIS_HOST}:{REDIS_PORT}/0',
#     include=['src.tasks.tasks']
# )

# celery.conf.update(
#     task_serializer='json',
#     accept_content=['json'],
#     result_serializer='json',
#     timezone='UTC',
#     enable_utc=True,
# )

# celery.conf.beat_schedule = {
#     'delete-expired-links-every-hour': {
#         'task': 'src.tasks.tasks.delete_expired_links',
#         'schedule': crontab(minute=0),  # каждый час
#     },
#     'cleanup-unused-links-daily': {
#         'task': 'src.tasks.tasks.cleanup_unused_links',
#         'schedule': crontab(hour=0, minute=0),  # каждый день в полночь
#     },
# }
