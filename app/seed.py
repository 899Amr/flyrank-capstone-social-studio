from datetime import datetime, timedelta, timezone

from app.main import service
from app.models import CampaignCreate, Platform


def main() -> None:
    service.store_token(Platform.instagram, "fake-instagram-token")
    service.store_token(Platform.x, "fake-x-token")
    campaign = service.create_campaign(
        CampaignCreate(
            title="Reliable publishing is a product feature",
            body="A campaign publisher must survive retries, rate limits, restarts, and untrusted callbacks without creating duplicates.",
            url="https://example.com/reliable-publishing",
        )
    )
    service.schedule(campaign["id"], datetime.now(timezone.utc) + timedelta(seconds=10))
    print({"campaign_id": campaign["id"], "scheduled_in_seconds": 10})


if __name__ == "__main__":
    main()


