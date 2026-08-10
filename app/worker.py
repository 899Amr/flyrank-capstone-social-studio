import time

from app.config import settings
from app.main import service


def main() -> None:
    while True:
        result = service.publish_due()
        if result["claimed"]:
            print(result, flush=True)
        time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    main()


