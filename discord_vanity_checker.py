#!/usr/bin/env python3
"""
Discord Vanity URL Checker - FAST & OPTIMIZED
==============================================
Checks Discord server vanity URLs (discord.gg/VANITY) for availability.
Uses real English words instead of random combinations.
NO TOKEN REQUIRED - Uses only proxies for checking.

WARNING: This may violate Discord's Terms of Service.

Installation:
    pip install requests[socks] pysocks tqdm

Usage:
    python discord_vanity_checker.py
"""

import argparse
import json
import time
import random
from datetime import datetime
from typing import List
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from queue import Queue

import requests
from tqdm import tqdm


# Discord API Configuration
DISCORD_API_BASE = "https://discord.com/api/v9"
VANITY_CHECK_ENDPOINT = f"{DISCORD_API_BASE}/invites"

# Thread-safe file writing and proxy rotation
file_lock = Lock()
stats_lock = Lock()
proxy_queue = Queue()


def load_word_list(lengths: List[int]) -> List[str]:
    """
    Load English words for vanity checking.
    
    Args:
        lengths: List of word lengths to include (e.g., [3, 4, 5])
    
    Returns:
        List of words to check
    """
    length_str = ", ".join(map(str, lengths))
    print(f"📚 Loading ALL word list ({length_str} letter words)...")
    
    all_words = set()
    
    # Source 1: Full English dictionary for MAXIMUM coverage
    try:
        response = requests.get(
            "https://raw.githubusercontent.com/dwyl/english-words/master/words_alpha.txt",
            timeout=10
        )
        words = response.text.strip().split("\n")
        for w in words:
            w = w.strip().lower()
            if len(w) in lengths and w.isalpha():
                all_words.add(w)
        print(f"   ✓ Loaded {len(all_words):,} words from full dictionary")
    except Exception as e:
        print(f"   ⚠️ Failed to load dictionary: {e}")
    
    # Source 2: Google's most common words
    try:
        response = requests.get(
            "https://raw.githubusercontent.com/first20hours/google-10000-english/master/google-10000-english-no-swears.txt",
            timeout=10
        )
        words = response.text.strip().split("\n")
        for w in words:
            w = w.strip().lower()
            if len(w) in lengths and w.isalpha():
                all_words.add(w)
        print(f"   ✓ Total words now: {len(all_words):,}")
    except:
        pass
    
    # Source 3: More common words
    try:
        response = requests.get(
            "https://raw.githubusercontent.com/first20hours/google-10000-english/master/google-10000-english-usa-no-swears.txt",
            timeout=10
        )
        words = response.text.strip().split("\n")
        for w in words:
            w = w.strip().lower()
            if len(w) in lengths and w.isalpha():
                all_words.add(w)
        print(f"   ✓ Final total: {len(all_words):,} words")
    except:
        pass
    
    if all_words:
        word_list = list(all_words)
        random.shuffle(word_list)
        print(f"✅ Loaded {len(word_list):,} TOTAL words ({length_str} letters)\n")
        return word_list
    
    print(f"⚠️  Failed to load online word lists")
    print("   Using fallback word generation...\n")
    
    # Fallback: common words of various lengths
    common_words = {
        3: ["ace", "aim", "air", "art", "bad", "ban", "bar", "bat", "bay", "bed",
            "bet", "big", "bit", "box", "boy", "bug", "bus", "buy", "car", "cat"],
        4: ["cool", "epic", "game", "play", "chat", "talk", "best", "fire", "hype",
            "vibe", "zone", "team", "clan", "crew", "gang", "wild", "dope", "sick",
            "lite", "dark", "moon", "star", "nova", "apex", "peak", "wave", "flow"],
        5: ["elite", "squad", "guild", "chill", "place", "space", "cyber", "hyper",
            "super", "ultra", "mega", "omega", "alpha", "delta", "sigma", "theta",
            "prime", "nexus", "chaos", "order", "magic", "power", "force", "storm"],
        6: ["gaming", "player", "master", "legend", "empire", "dragon", "knight",
            "wizard", "shadow", "phantom", "cosmic", "mystic", "frozen", "golden"],
        7: ["awesome", "amazing", "supreme", "ultimate", "perfect", "diamond",
            "crystal", "thunder", "warrior", "champion", "eternal", "infinite"]
    }
    
    fallback_words = []
    for length in lengths:
        if length in common_words:
            fallback_words.extend(common_words[length])
    
    random.shuffle(fallback_words)
    return fallback_words


def load_proxies(proxy_file: str) -> List[str]:
    """Load SOCKS4/SOCKS5 proxies from file."""
    print("🌐 Loading proxies...")
    proxies = []
    
    try:
        # Try to load from file
        with open(proxy_file, "r") as f:
            proxy_lines = f.read().strip().split("\n")
        
        for line in proxy_lines:
            line = line.strip()
            if line and not line.startswith("#"):
                # Auto-detect format and add socks4:// prefix
                if not line.startswith("socks"):
                    line = f"socks4://{line}"
                proxies.append(line)
        
        print(f"✅ Loaded {len(proxies)} SOCKS4 proxies from {proxy_file}")
        return proxies
    
    except FileNotFoundError:
        print(f"⚠️  Proxy file '{proxy_file}' not found!")
        print("   Create a file called 'proxies.txt' with one proxy per line (format: ip:port)")
        print("   Example:")
        print("   62.112.11.202:13037")
        print("   212.115.232.79:10800")
        return []
    except Exception as e:
        print(f"⚠️  Failed to load proxies: {e}")
        return []


def check_vanity(vanity: str, session: requests.Session, use_proxy: bool = True) -> tuple[bool, str]:
    """
    Check if a vanity URL is available - NO TOKEN NEEDED.
    
    Args:
        vanity: The vanity code to check
        session: Requests session
        use_proxy: Whether to use proxy (should always be True)
    
    Returns:
        Tuple of (is_available, status_message)
    """
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    # ALWAYS get proxy - NEVER use real IP
    proxies = None
    proxy_str = None
    
    if use_proxy:
        if proxy_queue.empty():
            # NO PROXY AVAILABLE - REFUSE TO MAKE REQUEST
            return False, "no_proxy_available"
        
        try:
            proxy_str = proxy_queue.get(timeout=0.01)
            proxies = {"http": proxy_str, "https": proxy_str}
        except:
            # NO PROXY AVAILABLE - REFUSE TO MAKE REQUEST
            return False, "no_proxy_available"
    else:
        # Proxy disabled but this is dangerous
        return False, "proxy_disabled"
    
    try:
        # Check if vanity exists (no authentication needed)
        check_url = f"{VANITY_CHECK_ENDPOINT}/{vanity}"
        response = session.get(check_url, proxies=proxies, timeout=5.0)  # Increased timeout
        
        # Return WORKING proxy to queue
        if proxy_str:
            try:
                proxy_queue.put(proxy_str, timeout=0.001)
            except:
                pass
        
        if response.status_code == 200:
            # Vanity exists and is taken
            return False, "taken"
        
        elif response.status_code == 404:
            # Vanity doesn't exist - AVAILABLE!
            return True, "available"
        
        elif response.status_code == 429:
            return False, "rate_limited"
        
        else:
            return False, "error"
    
    except requests.exceptions.ProxyError:
        # Don't return bad proxy to queue
        return False, "proxy_error"
    except requests.exceptions.Timeout:
        # Don't return slow proxy to queue
        return False, "timeout"
    except requests.exceptions.RequestException:
        # Don't return bad proxy to queue
        return False, "network_error"


def save_available_vanity(vanity: str):
    """Save available vanity URL to file based on word length."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    length = len(vanity)
    filename = f"{length}letter_vanity.txt"
    
    with file_lock:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"{vanity} | discord.gg/{vanity} | {timestamp}\n")
            f.flush()


def worker(vanity: str, delay: float, stats: dict, pbar: tqdm, use_proxy: bool = True) -> None:
    """Worker function for checking a single vanity - OPTIMIZED FOR SPEED."""
    session = requests.Session()
    session.trust_env = False
    
    is_available, status = check_vanity(vanity, session, use_proxy)
    
    # Retry on errors (up to 2 times)
    if status in ["network_error", "timeout", "proxy_error"]:
        is_available, status = check_vanity(vanity, session, use_proxy)
    
    if status in ["network_error", "timeout", "proxy_error"]:
        is_available, status = check_vanity(vanity, session, use_proxy)
    
    with stats_lock:
        stats['total_checked'] += 1
        
        # Show what we're checking
        if is_available:
            stats['available_count'] += 1
            save_available_vanity(vanity)
            tqdm.write(f"✅ AVAILABLE: {vanity} (discord.gg/{vanity})")
        elif status == "taken":
            stats['taken_count'] += 1
            tqdm.write(f"   {vanity} - taken")
        elif "rate_limited" in status:
            stats['rate_limit_count'] += 1
            tqdm.write(f"⏳ {vanity} - rate limited")
        elif "no_proxy_available" in status:
            stats['error_count'] += 1
            tqdm.write(f"   {vanity} - no proxy")
        elif status == "timeout":
            stats['error_count'] += 1
            tqdm.write(f"   {vanity} - timeout")
        elif status == "proxy_error":
            stats['error_count'] += 1
            tqdm.write(f"   {vanity} - proxy error")
        elif status == "network_error":
            stats['error_count'] += 1
            tqdm.write(f"   {vanity} - network error")
        else:
            stats['error_count'] += 1
            tqdm.write(f"   {vanity} - {status}")
        
        pbar.update(1)
        pbar.set_postfix({
            "Available": stats['available_count'],
            "Taken": stats['taken_count'],
            "RateLimits": stats['rate_limit_count']
        })
    
    time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(
        description="Discord Vanity URL Checker - NO TOKEN NEEDED"
    )
    
    parser.add_argument("--speed", type=int, default=500, help="Checks per second (default: 500)")
    parser.add_argument("--threads", type=int, help="Number of threads (auto-calculated, max 3000)")
    parser.add_argument("--count", type=int, help="Number of words to check (default: all)")
    parser.add_argument("--lengths", help="Word lengths to check (e.g., 3,4,5 or just 4). Leave empty to choose interactively.")
    parser.add_argument("--proxies", default="proxies.txt", help="Path to proxy list file (one per line, format: ip:port)")
    parser.add_argument("--no-proxies", action="store_true", help="⚠️ DANGEROUS: Disable proxies (uses your real IP)")
    
    args = parser.parse_args()
    
    print("\n" + "=" * 70)
    print("Discord Vanity URL Checker - NO TOKEN REQUIRED")
    print("=" * 70)
    print("This script checks vanity URL availability using ONLY proxies.")
    print("No Discord authentication needed!")
    print("=" * 70 + "\n")
    
    # Parse or ask for word lengths
    if args.lengths:
        try:
            lengths = [int(x.strip()) for x in args.lengths.split(",")]
        except ValueError:
            print("❌ Error: --lengths must be comma-separated integers (e.g., 3,4,5)")
            return
    else:
        print("Choose word lengths to check:")
        print("  Examples: 3,4,5  or  4  or  3,4,5,6,7")
        print("  Recommended: 4,5 (most common vanity lengths)")
        lengths_input = input("\nEnter word lengths (comma-separated): ").strip()
        
        if not lengths_input:
            lengths = [4, 5]  # Default
            print(f"Using default: {lengths}")
        else:
            try:
                lengths = [int(x.strip()) for x in lengths_input.split(",")]
            except ValueError:
                print("❌ Error: Invalid input. Using default: 4,5")
                lengths = [4, 5]
    
    print(f"\n✅ Checking words with {', '.join(map(str, lengths))} letters\n")
    
    # Load proxies - REQUIRED for IP protection
    use_proxies = not args.no_proxies
    
    if not use_proxies:
        print("\n" + "=" * 70)
        print("⚠️  CRITICAL WARNING: PROXY PROTECTION DISABLED!")
        print("=" * 70)
        print("You are about to make requests using YOUR REAL IP ADDRESS!")
        print("This will likely result in:")
        print("  • Your IP getting banned by Discord")
        print("  • Rate limits on your network")
        print("  • Possible account termination")
        print()
        print("It is STRONGLY RECOMMENDED to use proxies!")
        print("=" * 70 + "\n")
        
        response = input("Type 'USE MY IP' to continue without proxies: ")
        if response.strip() != "USE MY IP":
            print("\n✅ Smart choice! Please provide a proxy list.")
            print("   Create 'proxies.txt' with one proxy per line (format: ip:port)")
            return
    
    if use_proxies:
        proxies = load_proxies(args.proxies)
        if not proxies:
            print("\n❌ ERROR: No proxies loaded!")
            print("   Proxy protection is REQUIRED to avoid IP bans.")
            print("   Create 'proxies.txt' with your proxy list.")
            print("\n   Format (one per line):")
            print("   62.112.11.202:13037")
            print("   212.115.232.79:10800")
            return
        
        for proxy in proxies:
            proxy_queue.put(proxy)
        print(f"🛡️  IP PROTECTION: ENABLED ({len(proxies)} proxies loaded)")
        print(f"   Your real IP will NOT be used\n")
    else:
        print("⚠️  IP PROTECTION: DISABLED (using your real IP - DANGEROUS!)\n")
    
    # Load words with specified lengths
    words = load_word_list(lengths)
    
    if args.count:
        words = words[:args.count]
    
    print(f"🎯 Checking {len(words):,} words ({', '.join(map(str, lengths))} letters)\n")
    
    # Calculate speed
    speed = args.speed
    threads = args.threads if args.threads else min(speed * 4, 3000)  # 4x threads for max speed
    delay = max(0.00001, 0.3 / speed)  # Ultra minimal delay
    
    # Create output files for each length
    output_files = []
    for length in lengths:
        filename = f"{length}letter_vanity.txt"
        output_files.append(filename)
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"# Discord Vanity Checker - Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Checking {length}-letter vanity URLs\n")
            f.write(f"# Format: vanity | full_url | timestamp\n")
            f.write("#" + "=" * 67 + "\n\n")
            f.flush()
    
    print(f"📝 Output files: {', '.join(output_files)}\n")
    
    # Statistics
    stats = {
        'total_checked': 0,
        'available_count': 0,
        'taken_count': 0,
        'error_count': 0,
        'rate_limit_count': 0
    }
    
    print(f"🚀 Starting vanity check with {threads} threads...")
    print(f"   Total vanities: {len(words):,}")
    print(f"   Target speed: ~{speed} checks/second")
    print(f"   Estimated time: {len(words) / speed / 60:.2f} minutes\n")
    
    # Progress bar
    with tqdm(total=len(words), desc="Checking", unit="vanity") as pbar:
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = []
            
            for vanity in words:
                future = executor.submit(worker, vanity, delay, stats, pbar, use_proxies)
                futures.append(future)
            
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    tqdm.write(f"⚠️  Thread error: {e}")
    
    # Final summary
    print("\n" + "=" * 70)
    print("📊 FINAL SUMMARY")
    print("=" * 70)
    print(f"Total checked:     {stats['total_checked']:,}")
    print(f"Available:         {stats['available_count']:,}")
    print(f"Taken:             {stats['taken_count']:,}")
    print(f"Rate limits hit:   {stats['rate_limit_count']:,}")
    print(f"Errors:            {stats['error_count']:,}")
    print(f"\n✅ Available vanities saved to:")
    for filename in output_files:
        print(f"   - {filename}")
    print("=" * 70 + "\n")
    
    # Keep window open
    input("Press Enter to exit...")


if __name__ == "__main__":
    main()
