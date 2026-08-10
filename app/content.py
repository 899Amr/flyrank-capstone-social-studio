from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

from app.models import Platform


BRAND_VOICE = "Clear, useful, confident, and specific. Never use empty hype."
PLATFORM_RULES = {
    Platform.instagram: "Warm and visual. Use a short hook, two compact paragraphs, and three relevant hashtags.",
    Platform.x: "Direct and concise. Lead with the insight, stay under 280 characters, and use at most one hashtag.",
}


def compose_caption(platform: Platform, title: str, body: str, url: str) -> str:
    summary = " ".join(body.split())[:150]
    if platform == Platform.instagram:
        return (
            f"{title}\n\n{summary}...\n\nRead the full story: {url}\n"
            "#ContentStrategy #SocialMedia #FlyRank"
        )
    caption = f"{title}: {summary}... {url} #FlyRank"
    return caption[:280]


def prompt_components(platform: Platform, title: str, body: str) -> dict[str, str]:
    return {
        "brand_voice": BRAND_VOICE,
        "platform_rules": PLATFORM_RULES[platform],
        "content_summary": f"{title}: {' '.join(body.split())[:300]}",
    }


def source_placeholder(path: Path, title: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    image = Image.new("RGB", (1800, 1200), "#0c2423")
    draw = ImageDraw.Draw(image)
    draw.ellipse((650, 250, 1150, 750), fill="#48d597")
    draw.rectangle((0, 930, 1800, 1200), fill="#123b38")
    font = ImageFont.load_default(size=42)
    draw.text((90, 985), title[:55], fill="white", font=font)
    image.save(path, quality=92)
    return path


def generate_variants(source: Path, output_dir: Path) -> dict[Platform, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    specs = {Platform.instagram: (1080, 1080), Platform.x: (1600, 900)}
    results: dict[Platform, Path] = {}
    with Image.open(source) as image:
        image = image.convert("RGB")
        for platform, size in specs.items():
            variant = ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.45))
            target = output_dir / f"{platform.value}.jpg"
            variant.save(target, quality=90)
            results[platform] = target
    return results

