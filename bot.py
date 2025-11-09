import discord
from discord.ext import commands
from discord import app_commands
import os, json, datetime, asyncio

# ==========================
# BASIC CONFIG
# ==========================
TICKET_CATEGORY = "Tickets"
STAFF_ROLE = "Staff"
LOG_CHANNEL = "ticket-logs"
VERIFICATION_CHANNEL_ID = 1437035128802246697
COOLDOWN_HOURS = 48

# ==========================
# BOT SETUP
# ==========================
intents = discord.Intents.default()
intents.messages = True
intents.guilds = True
intents.members = True
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents)

# Cooldown memory
user_cooldowns = {}

# ==========================
# JSON HELPERS
# ==========================
def load_apps():
    if not os.path.exists("apps.json"):
        with open("apps.json", "w") as f:
            json.dump([], f)
    with open("apps.json", "r") as f:
        return json.load(f)

# ==========================
# EMBED HELPER
# ==========================
def make_embed(title: str, desc: str, color=discord.Color.blurple()):
    embed = discord.Embed(title=title, description=desc, color=color)
    embed.set_footer(text="💎 RASH TECH | Premium Support")
    return embed

# ==========================
# ON READY (Enhanced with Ticket Booth)
# ==========================
TICKET_BOOTH_CHANNEL_ID = 1431633723467501769  # 📩 Ticket Booth channel ID

class CreateTicketButton(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="🎟️ Create Ticket", style=discord.ButtonStyle.blurple, emoji="💎")
    async def create_ticket_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await ticket(interaction)  # reuse your existing /ticket command logic


@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        await bot.tree.sync()
        print("✅ Slash commands synced successfully.")
    except Exception as e:
        print(f"❌ Slash command sync error: {e}")

    # Get the ticket booth channel
    channel = bot.get_channel(TICKET_BOOTH_CHANNEL_ID)
    if channel:
        # Optional: clear old bot messages for a clean look
        async for msg in channel.history(limit=20):
            if msg.author == bot.user:
                await msg.delete()

        # Create the premium embed
        embed = discord.Embed(
            title="💎 Welcome to RASH TECH Premium Apps",
            description=(
                "🎉 **Get access to our Premium Apps Collection!**\n\n"
                "💠 Available apps:\n"
                "🎧 Spotify\n🏰 Castle\n🔥 Hotstar\n📞 Truecaller\n▶️ YouTube\n\n"
                "📩 To get your premium app, simply click the **button below** to create a private support ticket.\n\n"
                "Our team will verify your request and send your premium app link once confirmed 🚀"
            ),
            color=discord.Color.blurple()
        )
        embed.set_footer(text="💎 RASH TECH | Premium App Request System")
        embed.set_thumbnail(url="https://cdn-icons-png.flaticon.com/512/888/888879.png")

        view = CreateTicketButton()
        await channel.send(embed=embed, view=view)
        print("✅ Ticket Booth message sent successfully!")

# ==========================
# /TICKET COMMAND
# ==========================
@bot.tree.command(name="ticket", description="🎟️ Create a private support ticket.")
async def ticket(interaction: discord.Interaction):
    user = interaction.user
    guild = interaction.guild
    now = datetime.datetime.utcnow()

    # Cooldown check
    if user.id in user_cooldowns:
        diff = now - user_cooldowns[user.id]
        if diff.total_seconds() < COOLDOWN_HOURS * 3600:
            remaining = COOLDOWN_HOURS - (diff.total_seconds() / 3600)
            embed = make_embed(
                "⏳ Cooldown Active",
                f"You can create another ticket in **{int(remaining)} hours**.",
                discord.Color.orange()
            )
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

    # Check if already has ticket
    existing_channel = discord.utils.get(guild.channels, name=f"ticket-{user.name.lower()}")
    if existing_channel:
        embed = make_embed("❗ Ticket Exists", "You already have an open ticket.", discord.Color.red())
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return

    category = discord.utils.get(guild.categories, name=TICKET_CATEGORY)
    if not category:
        category = await guild.create_category(TICKET_CATEGORY)

    staff_role = discord.utils.get(guild.roles, name=STAFF_ROLE)

    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        user: discord.PermissionOverwrite(view_channel=True, send_messages=True, attach_files=True),
        staff_role: discord.PermissionOverwrite(view_channel=True, send_messages=True)
    }

    channel = await guild.create_text_channel(
        name=f"ticket-{user.name}",
        category=category,
        overwrites=overwrites,
        topic=f"Ticket for {user.display_name}"
    )

    # Record cooldown start
    user_cooldowns[user.id] = now

    # Welcome message
    welcome_embed = make_embed(
        "🎉 Welcome to RASH TECH Support!",
        f"Hey {user.mention}, our support team will assist you soon.\n\n"
        "Please read the below message to get started 👇",
        discord.Color.green()
    )
    await channel.send(embed=welcome_embed)

    # Apps info message
    app_list = "🎧 **Spotify**\n🏰 **Castle**\n🔥 **Hotstar**\n📞 **Truecaller**\n▶️ **YouTube**"
    apps_embed = make_embed(
        "💎 Currently Available Premium Apps",
        f"{app_list}\n\nType the **app name** you want below to start verification.\nNew apps will be added soon 🚀",
        discord.Color.gold()
    )
    await channel.send(embed=apps_embed)

    log_channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL)
    if log_channel:
        log_embed = make_embed(
            "🆕 New Ticket Created",
            f"{user.mention} created {channel.mention}",
            discord.Color.blurple()
        )
        await log_channel.send(embed=log_embed)

    # Notify user
    created_embed = make_embed("✅ Ticket Created", f"Your ticket: {channel.mention}", discord.Color.green())
    await interaction.response.send_message(embed=created_embed, ephemeral=True)

# ==========================
# /REMOVE_COOLDOWN COMMAND (Admin)
# ==========================
@bot.tree.command(name="remove_cooldown", description="🛠️ Remove a user's 48h cooldown (Admin only)")
@commands.has_permissions(administrator=True)
async def remove_cooldown(interaction: discord.Interaction, user: discord.User):
    if user.id in user_cooldowns:
        del user_cooldowns[user.id]
        embed = make_embed("✅ Cooldown Removed", f"{user.mention} can now open a new ticket.", discord.Color.green())
    else:
        embed = make_embed("ℹ️ No Cooldown Found", f"{user.mention} had no active cooldown.", discord.Color.orange())
    await interaction.response.send_message(embed=embed)

# ==========================
# MESSAGE HANDLER (App Keyword Detection)
# ==========================
@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Only react inside ticket channels
    if not message.channel.name.startswith("ticket-"):
        return

    # Detect if message contains app name
    apps = [a["name"].lower() for a in load_apps()]
    msg_lower = message.content.lower().strip()
    if msg_lower in apps:
        app_name = msg_lower.capitalize()
        verify_embed = make_embed(
            f"🧾 Verification Required for {app_name}",
            "📢 Please follow the steps below:\n"
            "1️⃣ Subscribe to our official channel.\n"
            "2️⃣ Take a **screenshot** of your subscription.\n"
            "3️⃣ Upload it here in this ticket.\n\n"
            "Once uploaded, we'll verify it and deliver your app link 💎",
            discord.Color.orange()
        )
        await message.channel.send(embed=verify_embed)
        message.channel.app_request = app_name  # Save chosen app temporarily
    await bot.process_commands(message)
    # ==========================
# PREMIUM TICKET LOGGING (UPGRADED)
# ==========================
async def send_ticket_log(channel: discord.TextChannel, user: discord.User, transcript_text: str):
    guild = channel.guild
    log_channel = discord.utils.get(guild.text_channels, name=LOG_CHANNEL)
    if not log_channel:
        return

    embed = discord.Embed(
        title="📜 Ticket Closed",
        description=f"🎫 **Ticket:** {channel.name}\n"
                    f"👤 **User:** {user.mention}\n"
                    f"🕒 **Closed:** <t:{int(datetime.datetime.utcnow().timestamp())}:R>\n\n"
                    f"💬 **Transcript:**\n```\n{transcript_text[:3900]}\n```",
        color=discord.Color.red(),
        timestamp=datetime.datetime.utcnow()
    )
    embed.set_author(name=f"{user.display_name}", icon_url=user.display_avatar.url)
    embed.set_footer(text="💎 RASH TECH | Ticket Log System")

    await log_channel.send(embed=embed)


# Overwrite the ConfirmClose.confirm() function
class ConfirmClose(discord.ui.View):
    def __init__(self, channel: discord.TextChannel, user: discord.User):
        super().__init__(timeout=60)
        self.channel = channel
        self.user = user

    @discord.ui.button(label="✅ Yes, Close", style=discord.ButtonStyle.danger, emoji="🔒")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.user:
            await interaction.response.send_message(
                embed=make_embed("🚫 Not Your Ticket", "Only the ticket creator can close this ticket."),
                ephemeral=True
            )
            return

        await interaction.response.send_message(
            embed=make_embed("⏳ Closing Ticket", "This ticket will close in **5 seconds**...")
        )
        await asyncio.sleep(5)

        messages = [
            f"{m.author.display_name}: {m.content}"
            async for m in self.channel.history(limit=None, oldest_first=True)
        ]
        transcript_text = "\n".join(messages)

        await send_ticket_log(self.channel, self.user, transcript_text)

        await self.channel.delete()

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary, emoji="↩️")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(
            embed=make_embed("👍 Cancelled", "Ticket will remain open."),
            ephemeral=True
        )


# ==========================
# KEEP-ALIVE SERVER (Flask)
# ==========================
from flask import Flask
from threading import Thread

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ RASH TECH Bot is alive!"

def run_web():
    app.run(host="0.0.0.0", port=8080)

def keep_alive():
    thread = Thread(target=run_web)
    thread.start()


# ==========================
# RUN BOT
# ==========================
if __name__ == "__main__":
    keep_alive()
    TOKEN = os.getenv("DISCORD_BOT_TOKEN")
    bot.run(TOKEN)
