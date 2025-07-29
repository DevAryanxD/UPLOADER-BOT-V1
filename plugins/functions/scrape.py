import logging
import asyncio
import os
import shutil
import json
from pyrogram import Client, enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from plugins.config import Config
from plugins.script import Translation
from plugins.thumbnail import Gthumb01, Gthumb02, Mdata01, Mdata03
from plugins.functions.display_progress import progress_for_pyrogram, humanbytes
from plugins.database.database import db
from plugins.functions.ran_text import random_char
logging.basicConfig(level=logging.DEBUG,
                    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def process_scrape(bot, user_id, scrape_channel, start_message_id, end_message_id):
    upload_channel = await db.get_upload_channel(user_id)
    chat_id = int(upload_channel) if upload_channel else user_id
    
    # Ensure start <= end
    start_id, end_id = min(start_message_id, end_message_id), max(start_message_id, end_message_id)
    
    status_message = await bot.send_message(
        chat_id=user_id,
        text="Scraping and downloading in progress...",
        disable_web_page_preview=True
    )
    
    for message_id in range(start_id, end_id + 1):
        try:
            message = await bot.get_messages(scrape_channel, message_id)
            if not message.text or not message.text.startswith('http'):
                logger.info(f"Skipping message ID {message_id}: Not a valid link")
                continue
                
            url = message.text
            youtube_dl_username = None
            youtube_dl_password = None
            custom_file_name = None
            
            if "|" in url:
                url_parts = url.split("|")
                if len(url_parts) == 2:
                    url, custom_file_name = url_parts
                elif len(url_parts) == 4:
                    url, custom_file_name, youtube_dl_username, youtube_dl_password = url_parts
                url = url.strip()
                if custom_file_name:
                    custom_file_name = custom_file_name.strip()
                if youtube_dl_username:
                    youtube_dl_username = youtube_dl_username.strip()
                if youtube_dl_password:
                    youtube_dl_password = youtube_dl_password.strip()
            else:
                for entity in message.entities or []:
                    if entity.type == "text_link":
                        url = entity.url
                    elif entity.type == "url":
                        o = entity.offset
                        l = entity.length
                        url = url[o:o + l]
            
            if not url:
                logger.info(f"Skipping message ID {message_id}: No valid URL")
                continue
                
            # Try yt-dlp first
            is_ytdl = await try_ytdl_download(bot, user_id, url, custom_file_name, youtube_dl_username, youtube_dl_password, chat_id, status_message)
            if not is_ytdl:
                # Fallback to direct download
                await try_direct_download(bot, user_id, url, custom_file_name, chat_id, status_message)
                
        except Exception as e:
            logger.error(f"Error processing message ID {message_id}: {e}")
            continue
    
    await status_message.edit(
        text="Scraping and downloading completed!",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 BACK", callback_data="home")]
        ])
    )

async def try_ytdl_download(bot, user_id, url, custom_file_name, username, password, chat_id, status_message):
    from datetime import datetime
    random1 = random_char(5)
    tmp_directory = os.path.join(Config.DOWNLOAD_LOCATION, f"{user_id}{random1}")
    os.makedirs(tmp_directory, exist_ok=True)
    
    # Run yt-dlp to get metadata
    command_to_exec = [
        "yt-dlp",
        "--no-warnings",
        "--allow-dynamic-mpd",
        "--no-check-certificate",
        "-j",
        url
    ]
    if Config.HTTP_PROXY:
        command_to_exec.extend(["--proxy", Config.HTTP_PROXY])
    if username:
        command_to_exec.extend(["--username", username])
    if password:
        command_to_exec.extend(["--password", password])
    
    process = await asyncio.create_subprocess_exec(
        *command_to_exec,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    e_response = stderr.decode().strip()
    t_response = stdout.decode().strip()
    
    if e_response and "nonnumeric port" not in e_response:
        logger.info(f"yt-dlp failed for {url}: {e_response}")
        return False
    
    if not t_response:
        return False
    
    response_json = json.loads(t_response.split("\n")[0] if "\n" in t_response else t_response)
    custom_file_name = custom_file_name or f"{response_json.get('title', 'file')}.mp4"
    download_directory = os.path.join(tmp_directory, custom_file_name)
    
    # Download with yt-dlp
    command_to_exec = [
        "yt-dlp",
        "-c",
        "--max-filesize", str(Config.TG_MAX_FILE_SIZE),
        "--embed-subs",
        "-f", "bestvideo+bestaudio/best",
        "--hls-prefer-ffmpeg",
        "--user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        url,
        "-o", download_directory
    ]
    if Config.HTTP_PROXY:
        command_to_exec.extend(["--proxy", Config.HTTP_PROXY])
    if username:
        command_to_exec.extend(["--username", username])
    if password:
        command_to_exec.extend(["--password", password])
    command_to_exec.append("--no-warnings")
    
    await status_message.edit(
        text=Translation.DOWNLOAD_START.format(custom_file_name)
    )
    start = datetime.now()
    
    process = await asyncio.create_subprocess_exec(
        *command_to_exec,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    e_response = stderr.decode().strip()
    
    if process.returncode != 0:
        logger.error(f"yt-dlp download failed for {url}: {e_response}")
        return False
    
    if not os.path.exists(download_directory):
        download_directory = os.path.splitext(download_directory)[0] + ".mkv"
        if not os.path.exists(download_directory):
            logger.error(f"Downloaded file not found: {download_directory}")
            return False
    
    file_size = os.stat(download_directory).st_size
    if file_size > Config.TG_MAX_FILE_SIZE:
        await status_message.edit(
            text=Translation.RCHD_TG_API_LIMIT.format((datetime.now() - start).seconds, humanbytes(file_size))
        )
        return False
    
    # Upload
    description = response_json.get("fulltitle", Translation.CUSTOM_CAPTION_UL_FILE)[:1021]
    await status_message.edit(
        text=Translation.UPLOAD_START.format(custom_file_name)
    )
    start_time = time.time()
    
    if not await db.get_upload_as_doc(user_id):
        thumbnail = await Gthumb01(bot, user_id)
        await bot.send_document(
            chat_id=chat_id,
            document=download_directory,
            thumb=thumbnail,
            caption=description,
            progress=progress_for_pyrogram,
            progress_args=(
                Translation.UPLOAD_START,
                status_message,
                start_time
            )
        )
    else:
        width, height, duration = await Mdata01(download_directory)
        thumb_image_path = await Gthumb02(bot, user_id, duration, download_directory)
        await bot.send_video(
            chat_id=chat_id,
            video=download_directory,
            caption=description,
            duration=duration,
            width=width,
            height=height,
            supports_streaming=True,
            thumb=thumb_image_path,
            progress=progress_for_pyrogram,
            progress_args=(
                Translation.UPLOAD_START,
                status_message,
                start_time
            )
        )
    
    try:
        shutil.rmtree(tmp_directory)
        if thumb_image_path and os.path.exists(thumb_image_path):
            os.remove(thumb_image_path)
    except Exception as e:
        logger.error(f"Error cleaning up: {e}")
        await bot.send_message(
            chat_id=user_id,
            text="Failed to clean up temporary files for one link. Continuing with next..."
        )
    
    return True

async def try_direct_download(bot, user_id, url, custom_file_name, chat_id, status_message):
    from datetime import datetime
    custom_file_name = custom_file_name or os.path.basename(url)
    tmp_directory = Config.DOWNLOAD_LOCATION + "/" + str(user_id)
    os.makedirs(tmp_directory, exist_ok=True)
    download_directory = tmp_directory + "/" + custom_file_name
    
    await status_message.edit(
        text=Translation.DOWNLOAD_START.format(custom_file_name)
    )
    start = datetime.now()
    
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, timeout=Config.PROCESS_MAX_TIMEOUT) as response:
                total_length = int(response.headers.get("Content-Length", 0))
                if "text" in response.headers.get("Content-Type", "") and total_length < 500:
                    logger.info(f"Skipping {url}: Invalid content type")
                    return False
                
                with open(download_directory, "wb") as f_handle:
                    downloaded = 0
                    async for chunk in response.content.iter_chunked(Config.CHUNK_SIZE):
                        f_handle.write(chunk)
                        downloaded += len(chunk)
                        now = time.time()
                        diff = now - start.total_seconds()
                        if round(diff % 5.00) == 0 or downloaded >= total_length:
                            percentage = downloaded * 100 / total_length if total_length else 0
                            await status_message.edit(
                                text="""**Download Status**
URL: {}
File Size: {}
Downloaded: {}
Percentage: {}%""".format(url, humanbytes(total_length), humanbytes(downloaded), round(percentage, 2))
                            )
        except Exception as e:
            logger.error(f"Direct download failed for {url}: {e}")
            return False
    
    if not os.path.exists(download_directory):
        logger.error(f"Downloaded file not found: {download_directory}")
        return False
    
    file_size = os.stat(download_directory).st_size
    if file_size > Config.TG_MAX_FILE_SIZE:
        await status_message.edit(
            text=Translation.RCHD_TG_API_LIMIT.format((datetime.now() - start).seconds, humanbytes(file_size))
        )
        return False
    
    await status_message.edit(
        text=Translation.UPLOAD_START.format(custom_file_name)
    )
    start_time = time.time()
    
    if not await db.get_upload_as_doc(user_id):
        thumbnail = await Gthumb01(bot, user_id)
        await bot.send_document(
            chat_id=chat_id,
            document=download_directory,
            thumb=thumbnail,
            caption=Translation.CUSTOM_CAPTION_UL_FILE,
            parse_mode=enums.ParseMode.HTML,
            progress=progress_for_pyrogram,
            progress_args=(
                Translation.UPLOAD_START,
                status_message,
                start_time
            )
        )
    else:
        width, height, duration = await Mdata01(download_directory)
        thumb_image_path = await Gthumb02(bot, user_id, duration, download_directory)
        await bot.send_video(
            chat_id=chat_id,
            video=download_directory,
            caption=Translation.CUSTOM_CAPTION_UL_FILE,
            duration=duration,
            width=width,
            height=height,
            supports_streaming=True,
            parse_mode=enums.ParseMode.HTML,
            thumb=thumb_image_path,
            progress=progress_for_pyrogram,
            progress_args=(
                Translation.UPLOAD_START,
                status_message,
                start_time
            )
        )
    
    try:
        os.remove(download_directory)
        if thumb_image_path and os.path.exists(thumb_image_path):
            os.remove(thumb_image_path)
    except Exception as e:
        logger.error(f"Error cleaning up: {e}")
        await bot.send_message(
            chat_id=user_id,
            text="Failed to clean up temporary files for one link. Continuing with next..."
        )
    
    return True