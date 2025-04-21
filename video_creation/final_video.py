import multiprocessing
import os
import re
import subprocess
import tempfile
import textwrap
import threading
import time
from os.path import exists  # Needs to be imported specifically
from pathlib import Path
from typing import Dict, Final, Tuple

import ffmpeg
import translators
from PIL import Image, ImageDraw, ImageFont
from rich.console import Console
from rich.progress import track

from utils import settings
from utils.cleanup import cleanup
from utils.console import print_step, print_substep
from utils.fonts import getheight
from utils.thumbnail import create_thumbnail
from utils.videos import save_data

console = Console()


class ProgressFfmpeg(threading.Thread):
    def __init__(self, vid_duration_seconds, progress_update_callback):
        threading.Thread.__init__(self, name="ProgressFfmpeg")
        self.stop_event = threading.Event()
        self.output_file = tempfile.NamedTemporaryFile(mode="w+", delete=False)
        self.vid_duration_seconds = vid_duration_seconds
        self.progress_update_callback = progress_update_callback

    def run(self):
        while not self.stop_event.is_set():
            latest_progress = self.get_latest_ms_progress()
            if latest_progress is not None:
                completed_percent = latest_progress / self.vid_duration_seconds
                self.progress_update_callback(completed_percent)
            time.sleep(1)

    def get_latest_ms_progress(self):
        lines = self.output_file.readlines()

        if lines:
            for line in lines:
                if "out_time_ms" in line:
                    out_time_ms_str = line.split("=")[1].strip()
                    if out_time_ms_str.isnumeric():
                        return float(out_time_ms_str) / 1000000.0
                    else:
                        # Handle the case when "N/A" is encountered
                        return None
        return None

    def stop(self):
        self.stop_event.set()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args, **kwargs):
        self.stop()


def name_normalize(name: str) -> str:
    name = re.sub(r'[?\\"%*:|<>]', "", name)
    name = re.sub(r"( [w,W]\s?\/\s?[o,O,0])", r" without", name)
    name = re.sub(r"( [w,W]\s?\/)", r" with", name)
    name = re.sub(r"(\d+)\s?\/\s?(\d+)", r"\1 of \2", name)
    name = re.sub(r"(\w+)\s?\/\s?(\w+)", r"\1 or \2", name)
    name = re.sub(r"\/", r"", name)

    lang = settings.config["reddit"]["thread"]["post_lang"]
    if lang:
        print_substep("Translating filename...")
        translated_name = translators.translate_text(name, translator="google", to_language=lang)
        return translated_name
    else:
        return name


def prepare_background(reddit_id: str, W: int, H: int) -> str:
    output_path = f"assets/temp/{reddit_id}/background_noaudio.mp4"
    output = (
        ffmpeg.input(f"assets/temp/{reddit_id}/background.mp4")
        .filter("crop", f"ih*({W}/{H})", "ih")
        .output(
            output_path,
            an=None,
            **{
                "c:v": "h264",
                "b:v": "20M",
                "b:a": "192k",
                "threads": multiprocessing.cpu_count(),
            },
        )
        .overwrite_output()
    )
    try:
        output.run(quiet=True)
    except ffmpeg.Error as e:
        print(e.stderr.decode("utf8"))
        exit(1)
    return output_path


def create_fancy_thumbnail(image, text, text_color, padding, wrap=35):
    print_step(f"Creating fancy thumbnail for: {text}")
    font_title_size = 47
    font = ImageFont.truetype(os.path.join("fonts", "Roboto-Bold.ttf"), font_title_size)
    image_width, image_height = image.size
    lines = textwrap.wrap(text, width=wrap)
    y = (
        (image_height / 2)
        - (((getheight(font, text) + (len(lines) * padding) / len(lines)) * len(lines)) / 2)
        + 30
    )
    draw = ImageDraw.Draw(image)

    username_font = ImageFont.truetype(os.path.join("fonts", "Roboto-Bold.ttf"), 30)
    draw.text(
        (205, 825),
        settings.config["settings"]["channel_name"],
        font=username_font,
        fill=text_color,
        align="left",
    )

    if len(lines) == 3:
        lines = textwrap.wrap(text, width=wrap + 10)
        font_title_size = 40
        font = ImageFont.truetype(os.path.join("fonts", "Roboto-Bold.ttf"), font_title_size)
        y = (
            (image_height / 2)
            - (((getheight(font, text) + (len(lines) * padding) / len(lines)) * len(lines)) / 2)
            + 35
        )
    elif len(lines) == 4:
        lines = textwrap.wrap(text, width=wrap + 10)
        font_title_size = 35
        font = ImageFont.truetype(os.path.join("fonts", "Roboto-Bold.ttf"), font_title_size)
        y = (
            (image_height / 2)
            - (((getheight(font, text) + (len(lines) * padding) / len(lines)) * len(lines)) / 2)
            + 40
        )
    elif len(lines) > 4:
        lines = textwrap.wrap(text, width=wrap + 10)
        font_title_size = 30
        font = ImageFont.truetype(os.path.join("fonts", "Roboto-Bold.ttf"), font_title_size)
        y = (
            (image_height / 2)
            - (((getheight(font, text) + (len(lines) * padding) / len(lines)) * len(lines)) / 2)
            + 30
        )

    for line in lines:
        draw.text((120, y), line, font=font, fill=text_color, align="left")
        y += getheight(font, line) + padding

    return image


def merge_background_audio(audio: ffmpeg, reddit_id: str):
    """Gather an audio and merge with assets/backgrounds/background.mp3
    Args:
        audio (ffmpeg): The TTS final audio but without background.
        reddit_id (str): The ID of subreddit
    """
    background_audio_volume = settings.config["settings"]["background"]["background_audio_volume"]
    if background_audio_volume == 0:
        return audio  # Return the original audio
    else:
        # sets volume to config
        bg_audio = ffmpeg.input(f"assets/temp/{reddit_id}/background.mp3").filter(
            "volume",
            background_audio_volume,
        )
        # Merges audio and background_audio
        merged_audio = ffmpeg.filter([audio, bg_audio], "amix", duration="longest")
        return merged_audio  # Return merged audio


def make_final_video(number_of_comments, length, reddit_object, bg_config):
    """
    Combines audio, video, and subtitles into the final video.
    Uses predefined paths for video, audio, and subtitles.
    """
    reddit_id = id(reddit_object)
    temp_dir = f"assets/temp/{reddit_id}/"
    subtitles_path = f"assets/backgrounds/subtitles/subtitle{reddit_id}.srt"  # Updated path for subtitles
    output_path = f"{temp_dir}final_video.mp4"  # Path to the final video

    # Use predefined paths for video and audio
    video_path = "assets/backgrounds/video/bbswitzer-parkour.mp4"  # Path to the background video
    audio_path = "assets/backgrounds/audio/Super Lofi World-lofi.mp3"  # Path to the background audio

    # Check if required files exist
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Video file not found: {video_path}")
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"Audio file not found: {audio_path}")
    if not os.path.exists(subtitles_path):
        raise FileNotFoundError(f"Subtitles file not found: {subtitles_path}")

    # Use FFmpeg to combine video, audio, and subtitles
    subprocess.run([
        "ffmpeg",
        "-i", video_path,  # Input video
        "-i", audio_path,  # Input audio
        "-vf", f"subtitles={subtitles_path}",  # Add subtitles
        "-c:v", "libx264",  # Video codec
        "-c:a", "aac",  # Audio codec
        "-strict", "experimental",  # Allow experimental features
        output_path  # Output file
    ], check=True)

    print(f"Final video created at {output_path}")
