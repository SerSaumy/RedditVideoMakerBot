# filepath: c:\Users\saumy\Documents\GitHub\RedditVideoMakerBot\video_creation\subtitle_generator.py
from pathlib import Path

def generate_subtitles(reddit_object: dict, output_path: str) -> None:
    """
    Generates subtitles from the Reddit post and comments.

    Args:
        reddit_object (dict): Reddit object containing the post and comments.
        output_path (str): Path to save the subtitles file.
    """
    subtitles = []
    timestamp = 0

    # Add the post title
    subtitles.append(f"1\n00:00:00,000 --> 00:00:05,000\n{reddit_object['thread_title']}\n")

    # Add comments as subtitles
    for idx, comment in enumerate(reddit_object["comments"]):
        start_time = timestamp
        end_time = timestamp + 5  # Each comment lasts 5 seconds
        subtitles.append(
            f"{idx + 2}\n00:00:{start_time:02},000 --> 00:00:{end_time:02},000\n{comment['comment_body']}\n"
        )
        timestamp += 5

    # Save subtitles to file
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.writelines(subtitles)

    print(f"Subtitles successfully generated at: {output_path}")  # Debugging line