# filepath: c:\Users\saumy\Documents\GitHub\RedditVideoMakerBot\video_creation\subtitle_generator.py
from pathlib import Path
from pysrt import SubRipFile

def generate_subtitles(reddit_object: dict, output_path: str) -> None:
    """
    Generates dynamic subtitles from the Reddit post and comments.
    """
    subtitles = SubRipFile()
    start_time = 0.0

    for comment in reddit_object["comments"]:
        duration = len(comment) * 0.05  # Approximate duration based on text length
        subtitles.append({
            "start": start_time,
            "end": start_time + duration,
            "text": f"<font color='yellow' size='24'>{comment}</font>"
        })
        start_time += duration

    subtitles.save(output_path, encoding="utf-8")