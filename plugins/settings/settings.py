import asyncio
from pyrogram import types, errors, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from plugins.config import Config
from plugins.database.database import db
from plugins.database.add import AddUser
from pyrogram import Client

async def OpenSettings(m: "types.Message"):
    usr_id = m.chat.id
    user_data = await db.get_user_data(usr_id)
    if not user_data:
        await m.edit("Failed to fetch your data from database!")
        return
    upload_as_doc = user_data.get("upload_as_doc", False)
    thumbnail = user_data.get("thumbnail", None)
    upload_channel = user_data.get("upload_channel", None)
    
    # Set button text based on upload channel
    upload_button_text = f"📤 Upload: {'DM' if upload_channel is None else upload_channel}"
    
    buttons_markup = [
        [types.InlineKeyboardButton(f" {'📹 VIDEO' if upload_as_doc else '📁 DOCUMENT'}",
                                    callback_data="triggerUploadMode")],
        [types.InlineKeyboardButton(f"{'🏞 CHANGE' if thumbnail else '🏞 SET'} THUMBNAIL",
                                    callback_data="setThumbnail")],
        [types.InlineKeyboardButton(upload_button_text,
                                    callback_data="setUploadChannel")]
    ]
    if thumbnail:
        buttons_markup.append([types.InlineKeyboardButton("🏞 SHOW THUMBNAIL",
                                                          callback_data="showThumbnail")])
    buttons_markup.append([types.InlineKeyboardButton("🔙 BACK", 
                                                      callback_data="home")])

    try:
        await m.edit(
            text="**CURRENT SETTINGS 👇**",
            reply_markup=types.InlineKeyboardMarkup(buttons_markup),
            disable_web_page_preview=True,
        )
    except errors.MessageNotModified:
        pass
    except errors.FloodWait as e:
        await asyncio.sleep(e.x)
        await OpenSettings(m)
    except Exception as err:
        Config.LOGGER.getLogger(__name__).error(err)

@Client.on_message(filters.private & filters.command("settings"))
async def settings_handler(bot: Client, m: Message):
    await AddUser(bot, m)
    editable = await m.reply_text("**Checking...**", quote=True)
    await OpenSettings(editable)

@Client.on_callback_query(filters.regex('^setUploadChannel$'))
async def set_upload_channel(bot, update):
    await update.answer()
    await update.message.edit(
        text="**Please follow these steps to set a custom upload channel:**\n\n"
             "1. Create a new Telegram channel (public or private).\n"
             "2. Add this bot (@{}) as an admin with full privileges (post messages, edit messages, etc.).\n"
             "3. Send the channel ID (e.g., -1001234567890) here.".format(Config.BOT_USERNAME),
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("🔙 BACK", callback_data="OpenSettings")]
        ]),
        disable_web_page_preview=True
    )
    # Force reply to capture channel ID
    await bot.send_message(
        chat_id=update.from_user.id,
        text="Send the channel ID now:",
        reply_markup=types.ForceReply()
    )

@Client.on_message(filters.private & filters.reply & filters.regex(r'^-100[0-9]+$'))
async def handle_channel_id(bot, message):
    if not message.reply_to_message or not message.reply_to_message.from_user.is_self:
        return
    channel_id = message.text.strip()
    user_id = message.from_user.id
    
    try:
        # Verify bot is admin in the channel
        chat_member = await bot.get_chat_member(int(channel_id), bot.me.id)
        if chat_member.status != 'administrator':
            await message.reply_text(
                "Please make me an admin with full privileges in the channel and try again.",
                reply_markup=InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔙 BACK", callback_data="OpenSettings")]
                ])
            )
            return
        
        # Store channel ID in database
        await db.set_upload_channel(user_id, channel_id)
        await message.reply_text(
            f"Successfully set upload channel to {channel_id}!\nFiles will now be uploaded there.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 BACK", callback_data="OpenSettings")]
            ])
        )
        # Refresh settings menu
        await OpenSettings(message)
        
    except (errors.PeerIdInvalid, errors.ChatAdminRequired):
        await message.reply_text(
            "Invalid channel ID or I'm not an admin in that channel. Please check and try again.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 BACK", callback_data="OpenSettings")]
            ])
        )
    except Exception as e:
        Config.LOGGER.getLogger(__name__).error(f"Error setting channel: {e}")
        await message.reply_text(
            "An error occurred. Please try again or contact support.",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🔙 BACK", callback_data="OpenSettings")]
            ])
  )
