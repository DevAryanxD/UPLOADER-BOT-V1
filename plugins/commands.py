import random
import os
import time
import psutil
import shutil
import string
import asyncio
from pyrogram import Client, filters
from asyncio import TimeoutError
from pyrogram.types import Message 
from pyrogram.errors import MessageNotModified
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message, CallbackQuery, ForceReply
from plugins.config import Config
from plugins.script import Translation
from pyrogram import Client, filters
from plugins.database.add import AddUser
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from plugins.database.database import db
from plugins.functions.forcesub import handle_force_subscribe
from plugins.settings.settings import OpenSettings
from plugins.config import *
from plugins.functions.verify import verify_user, check_token
from pyrogram import types, errors

@Client.on_message(filters.private & filters.command(["start"]))
async def start(bot, update):
    if Config.UPDATES_CHANNEL is not None:
        fsub = await handle_force_subscribe(bot, update)
        if fsub == 400:
            return
    if len(update.command) != 2:
        await AddUser(bot, update)
        await update.reply_text(
            text=Translation.START_TEXT.format(update.from_user.mention),
            reply_markup=Translation.START_BUTTONS,
        )
        return
    data = update.command[1]
    if data.split("-", 1)[0] == "verify":
        userid = data.split("-", 2)[1]
        token = data.split("-", 3)[2]
        if str(update.from_user.id) != str(userid):
            return await update.reply_text(
                text="<b>Exᴘɪʀᴇᴅ Lɪɴᴋ Oʀ ⵊɴᴠᴀʟɪᴅ Lɪɴᴋ !</b>",
                protect_content=True
            )
        is_valid = await check_token(bot, userid, token)
        if is_valid == True:
            await update.reply_text(
                text=f"<b>Hᴇʏ {update.from_user.mention} 👋,\nʏᴏᴜ Aʀᴇ Sᴜᴄᴄᴇssғᴜʟʟʏ Vᴇʀɪғɪᴇᴅ !\n\nNᴏᴡ Yᴏᴜ Uᴘʟᴏᴀᴅ Fɪʟᴇs Aɴᴅ Vɪᴅᴇᴏs Tɪʟʟ Tᴏᴅᴀʏ Mɪᴅɴɪɢʜᴛ.</b>",
                protect_content=True
            )
            await verify_user(bot, userid, token)
        else:
            return await update.reply_text(
                text="<b>Exᴘɪʀᴇᴅ Lɪɴᴋ Oʀ ⵊɴᴠᴀʟɪᴅ Lɪɴᴋ !</b>",
                protect_content=True
            )

@Client.on_message(filters.command("help", [".", "/"]) & filters.private)
async def help_bot(_, m: Message):
    await AddUser(_, m)
    return await m.reply_text(
        Translation.HELP_TEXT,
        reply_markup=Translation.HELP_BUTTONS,
        disable_web_page_preview=True,
    )

@Client.on_message(filters.command("about", [".", "/"]) & filters.private)
async def aboutme(_, m: Message):
    await AddUser(_, m)
    return await m.reply_text(
        Translation.ABOUT_TEXT,
        reply_markup=Translation.ABOUT_BUTTONS,
        disable_web_page_preview=True,
    )

@Client.on_message(filters.private & filters.reply & filters.text)
async def edit_caption(bot, update):
    await AddUser(bot, update)
    try:
        await bot.send_cached_media(
            chat_id=update.chat.id,
            file_id=update.reply_to_message.video.file_id,
            caption=update.text
        )
    except:
        try:
            await bot.send_cached_media(
                chat_id=update.chat.id,
                file_id=update.reply_to_message.document.file_id,
                caption=update.text
            )
        except:
            pass

@Client.on_message(filters.private & filters.command(["caption"], [".", "/"]))
async def add_caption_help(bot, update):
    await AddUser(bot, update)
    await bot.send_message(
        chat_id=update.chat.id,
        text=Translation.ADD_CAPTION_HELP,
        reply_markup=Translation.BUTTONS,
    )

@Client.on_message(filters.private & filters.command("scrape_dl"))
async def scrape_dl_handler(bot, update):
    await AddUser(bot, update)
    await bot.send_message(
        chat_id=update.chat.id,
        text="Please send the channel or group ID (e.g., -1001234567890) where I should scrape download links. Ensure I'm an admin there with full privileges.",
        reply_markup=types.ForceReply()
    )

@Client.on_message(filters.private & filters.reply & filters.regex(r'^-100[0-9]+$'))
async def handle_scrape_channel_id(bot, message):
    if not message.reply_to_message or not message.reply_to_message.from_user.is_self:
        return
    channel_id = message.text.strip()
    user_id = message.from_user.id
    
    try:
        # Verify bot is admin in the channel
        chat_member = await bot.get_chat_member(int(channel_id), bot.me.id)
        if chat_member.status != 'administrator':
            await message.reply_text(
                "Please make me an admin with full privileges in the channel/group and try again.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 BACK", callback_data="home")]
                ])
            )
            return
        
        # Store scrape channel ID in database
        await db.set_scrape_channel(user_id, channel_id)
        await message.reply_text(
            "Successfully set scrape channel!\nSend /scrape to start scrape downloading.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 BACK", callback_data="home")]
            ])
        )
        
    except (errors.PeerIdInvalid, errors.ChatAdminRequired):
        await message.reply_text(
            "Invalid channel/group ID or I'm not an admin there. Please check and try again.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 BACK", callback_data="home")]
            ])
        )
    except Exception as e:
        Config.LOGGER.getLogger(__name__).error(f"Error setting scrape channel: {e}")
        await message.reply_text(
            "An error occurred. Please try again or contact support.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 BACK", callback_data="home")]
            ])
        )

@Client.on_message(filters.private & filters.command("scrape"))
async def scrape_handler(bot, update):
    await AddUser(bot, update)
    scrape_channel = await db.get_scrape_channel(update.from_user.id)
    if not scrape_channel:
        await update.reply_text(
            "Please set a scrape channel first using /scrape_dl.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 BACK", callback_data="home")]
            ])
        )
        return
    
    await bot.send_message(
        chat_id=update.chat.id,
        text="Please forward the first message from the scrape channel to start downloading.",
        reply_markup=types.ForceReply()
    )

@Client.on_message(filters.private & filters.forwarded & filters.reply)
async def handle_scrape_messages(bot, message):
    if not message.reply_to_message or not message.reply_to_message.from_user.is_self:
        return
    
    user_id = message.from_user.id
    scrape_channel = await db.get_scrape_channel(user_id)
    if not scrape_channel or str(message.forward_from_chat.id) != str(scrape_channel.replace('-100', '')):
        await message.reply_text(
            "Please forward a message from the set scrape channel.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 BACK", callback_data="home")]
            ])
        )
        return
    
    start_message_id = message.forward_from_message_id
    await message.reply_text(
        "Now forward the last message from the scrape channel to define the range.",
        reply_markup=types.ForceReply()
    )
    
    # Store start message ID temporarily
    await db.set_caption(user_id, start_message_id)  # Using caption field as temp storage
    
@Client.on_message(filters.private & filters.forwarded & filters.reply)
async def handle_scrape_range(bot, message):
    if not message.reply_to_message or not message.reply_to_message.from_user.is_self:
        return
    
    user_id = message.from_user.id
    scrape_channel = await db.get_scrape_channel(user_id)
    if not scrape_channel or str(message.forward_from_chat.id) != str(scrape_channel.replace('-100', '')):
        await message.reply_text(
            "Please forward a message from the set scrape channel.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 BACK", callback_data="home")]
            ])
        )
        return
    
    start_message_id = await db.get_caption(user_id)  # Retrieve temp stored start ID
    end_message_id = message.forward_from_message_id
    await db.set_caption(user_id, None)  # Clear temp storage
    
    await message.reply_text(
        f"Starting scrape download from message ID {start_message_id} to {end_message_id} in channel {scrape_channel}..."
    )
    
    # Call scrape processing function
    from plugins.functions.scrape import process_scrape
    await process_scrape(bot, user_id, scrape_channel, start_message_id, end_message_id)