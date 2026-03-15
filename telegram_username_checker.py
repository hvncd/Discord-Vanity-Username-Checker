#!/usr/bin/env python3
"""
Telegram Username Checker - FAST & OPTIMIZED
=============================================
Checks Telegram usernames (t.me/USERNAME) for availability.
Minimum 5 characters required by Telegram.
NO TOKEN REQUIRED - Uses only proxies.

WARNING: This may violate Telegram's Terms of Service.

Installation:
    pip install requests[socks] pysocks tqdm

Usage:
    python telegram_username_checker.py
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


# Telegram API Configuration
TELEGRAM_API_BASE = "https://t.me"

# Thread-safe file writing and proxy rotation
file_lock = Lock()
stats_lock = Lock()
proxy_queue = Queue()


def load_proxies(proxy_file: str = "proxies.txt") -> List[str]:
    """Load SOCKS4 proxies from file."""
    print("🌐 Loading proxies...")
    proxies = []
    
    try:
        with open(proxy_file, "r") as f:
            proxy_lines = f.read().strip().split("\n")
        
        for line in proxy_lines:
            line = line.strip()
            if line and not line.startswith("#"):
                if not line.startswith("socks"):
                    line = f"socks4://{line}"
                proxies.append(line)
        
        print(f"✅ Loaded {len(proxies)} SOCKS4 proxies from {proxy_file}")
        return proxies
    
    except FileNotFoundError:
        print(f"⚠️  Proxy file '{proxy_file}' not found!")
        print("   Create 'proxies.txt' with one proxy per line (format: ip:port)")
        return []
    except Exception as e:
        print(f"⚠️  Failed to load proxies: {e}")
        return []


def generate_random_combos(lengths: List[int], count: int = 10000) -> List[str]:
    """Generate RANDOMIZED username combinations."""
    characters = "abcdefghijklmnopqrstuvwxyz0123456789_"
    combos = []
    
    print("🔄 Generating RANDOMIZED username combinations...")
    
    seen = set()
    for length in lengths:
        length_count = count // len(lengths)
        while len([c for c in combos if len(c) == length]) < length_count:
            # Telegram usernames: must start with letter, can contain letters, numbers, underscores
            first_char = random.choice("abcdefghijklmnopqrstuvwxyz")
            rest = ''.join(random.choices(characters, k=length-1))
            username = first_char + rest
            
            if username not in seen:
                seen.add(username)
                combos.append(username)
    
    return combos


def load_word_list(lengths: List[int]) -> List[str]:
    """Load real English words for username checking."""
    length_str = ", ".join(map(str, lengths))
    print(f"📚 Loading word list ({length_str} character words)...")
    
    all_words = set()
    
    # Full English dictionary
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
        print(f"   ✓ Loaded {len(all_words):,} words from dictionary")
    except Exception as e:
        print(f"   ⚠️ Failed to load dictionary: {e}")
    
    # Google common words
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
        print(f"   ✓ Total words: {len(all_words):,}")
    except:
        pass
    
    if all_words:
        word_list = list(all_words)
        random.shuffle(word_list)
        return word_list
    
    # Fallback
    fallback = {
        5: ["admin", "super", "elite", "squad", "guild", "chill", "place", "space"],
        6: ["gaming", "player", "master", "legend", "empire", "dragon", "knight"],
        7: ["awesome", "amazing", "supreme", "perfect", "diamond", "crystal"]
    }
    
    result = []
    for length in lengths:
        if length in fallback:
            result.extend(fallback[length])
    
    random.shuffle(result)
    return result


def check_username(username: str, session: requests.Session, use_proxy: bool = True) -> tuple[bool, str]:
    """
    Check if a Telegram username is available - NO TOKEN NEEDED.
    Uses Telegram's public API.
    
    Args:
        username: The username to check
        session: Requests session
        use_proxy: Whether to use proxy
    
    Returns:
        Tuple of (is_available, status_message)
    """
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    }
    
    # ALWAYS get proxy - NEVER use real IP
    proxies = None
    proxy_str = None
    
    if use_proxy:
        if proxy_queue.empty():
            return False, "no_proxy_available"
        
        try:
            proxy_str = proxy_queue.get(timeout=0.01)
            proxies = {"http": proxy_str, "https": proxy_str}
        except:
            return False, "no_proxy_available"
    else:
        return False, "proxy_disabled"
    
    try:
        # Method 1: Try the direct page check (faster)
        check_url = f"{TELEGRAM_API_BASE}/{username}"
        response = session.head(check_url, headers=headers, proxies=proxies, timeout=8.0, allow_redirects=False)
        
        # Return WORKING proxy to queue
        if proxy_str:
            try:
                proxy_queue.put(proxy_str, timeout=0.001)
            except:
                pass
        
        # If we get a redirect or 200, the username exists (taken)
        if response.status_code in [200, 301, 302]:
            return False, "taken"
        
        # If we get 404, username doesn't exist (available)
        elif response.status_code == 404:
            return True, "available"
        
        elif response.status_code == 429:
            return False, "rate_limited"
        
        else:
            # Ambiguous response, do a full GET request
            response = session.get(check_url, headers=headers, proxies=proxies, timeout=8.0)
            
            if response.status_code == 200:
                content = response.text.lower()
                # Check for indicators that profile exists
                if "tgme_page" in content or "tgme_page_photo" in content:
                    return False, "taken"
                else:
                    return True, "available"
            elif response.status_code == 404:
                return True, "available"
            else:
                return False, "error"
    
    except requests.exceptions.ProxyError:
        # Return proxy anyway - might work next time
        if proxy_str:
            try:
                proxy_queue.put(proxy_str, timeout=0.001)
            except:
                pass
        return False, "proxy_error"
    except requests.exceptions.Timeout:
        # Return proxy anyway
        if proxy_str:
            try:
                proxy_queue.put(proxy_str, timeout=0.001)
            except:
                pass
        return False, "timeout"
    except requests.exceptions.RequestException as e:
        # Return proxy anyway
        if proxy_str:
            try:
                proxy_queue.put(proxy_str, timeout=0.001)
            except:
                pass
        return False, "network_error"


def save_available_username(username: str):
    """Save available username to file based on length."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    length = len(username)
    filename = f"{length}letter_telegram.txt"
    
    with file_lock:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"{username} | t.me/{username} | {timestamp}\n")
            f.flush()


def worker(username: str, delay: float, stats: dict, pbar: tqdm, use_proxy: bool = True) -> None:
    """Worker function for checking a single username."""
    session = requests.Session()
    session.trust_env = False
    
    is_available, status = check_username(username, session, use_proxy)
    
    # Retry up to 2 times on errors
    if status in ["network_error", "timeout", "proxy_error"]:
        time.sleep(0.2)  # Brief pause before retry
        is_available, status = check_username(username, session, use_proxy)
    
    if status in ["network_error", "timeout", "proxy_error"]:
        time.sleep(0.2)
        is_available, status = check_username(username, session, use_proxy)
    
    with stats_lock:
        stats['total_checked'] += 1
        
        if is_available:
            stats['available_count'] += 1
            save_available_username(username)
            tqdm.write(f"✅ AVAILABLE: {username} (t.me/{username})")
        elif status == "taken":
            stats['taken_count'] += 1
            tqdm.write(f"   {username} - taken")
        elif "rate_limited" in status:
            stats['rate_limit_count'] += 1
            tqdm.write(f"⏳ {username} - rate limited")
        elif "no_proxy_available" in status:
            stats['error_count'] += 1
            if stats['error_count'] == 1:
                tqdm.write(f"❌ No proxies available!")
        elif status == "timeout":
            stats['error_count'] += 1
            # Only show occasional timeout messages
            if stats['error_count'] % 50 == 1:
                tqdm.write(f"⚠️  Many timeouts - proxies may be slow")
        elif status == "proxy_error":
            stats['error_count'] += 1
            # Only show occasional proxy errors
            if stats['error_count'] % 50 == 1:
                tqdm.write(f"⚠️  Many proxy errors - some proxies may be dead")
        elif status == "network_error":
            stats['error_count'] += 1
            # Only show occasional network errors
            if stats['error_count'] % 50 == 1:
                tqdm.write(f"⚠️  Many network errors")
        else:
            stats['error_count'] += 1
            tqdm.write(f"   {username} - {status}")
        
        pbar.update(1)
        pbar.set_postfix({
            "Available": stats['available_count'],
            "Taken": stats['taken_count'],
            "RateLimits": stats['rate_limit_count']
        })
    
    time.sleep(delay)


def main():
    parser = argparse.ArgumentParser(
        description="Telegram Username Checker - NO TOKEN NEEDED"
    )
    
    parser.add_argument("--speed", type=int, default=1000, help="Checks per second (default: 1000)")
    parser.add_argument("--threads", type=int, help="Number of threads (auto-calculated, max 3000)")
    parser.add_argument("--count", type=int, help="Number of usernames to check (default: 10000)")
    parser.add_argument("--lengths", help="Username lengths to check (e.g., 5,6,7). Leave empty to choose interactively.")
    parser.add_argument("--proxies", default="proxies.txt", help="Path to proxy list file")
    parser.add_argument("--no-proxies", action="store_true", help="⚠️ DANGEROUS: Disable proxies")
    
    args = parser.parse_args()
    
    print("\n" + "=" * 70)
    print("Telegram Username Checker - NO TOKEN REQUIRED")
    print("=" * 70)
    print("Checks Telegram username availability using ONLY proxies.")
    print("Minimum 5 characters required by Telegram.")
    print("=" * 70 + "\n")
    
    # Parse or ask for username lengths
    if args.lengths:
        try:
            lengths = [int(x.strip()) for x in args.lengths.split(",")]
        except ValueError:
            print("❌ Error: --lengths must be comma-separated integers")
            return
    else:
        print("Choose username lengths to check (minimum 5):")
        print("  Examples: 5,6  or  5  or  5,6,7,8")
        print("  Recommended: 5,6 (shorter = more likely available)")
        lengths_input = input("\nEnter username lengths (comma-separated): ").strip()
        
        if not lengths_input:
            lengths = [5, 6]
            print(f"Using default: {lengths}")
        else:
            try:
                lengths = [int(x.strip()) for x in lengths_input.split(",")]
            except ValueError:
                print("❌ Error: Invalid input. Using default: 5,6")
                lengths = [5, 6]
    
    # Validate minimum length
    if any(l < 5 for l in lengths):
        print("❌ Error: Telegram usernames must be at least 5 characters!")
        return
    
    print(f"\n✅ Checking usernames with {', '.join(map(str, lengths))} characters\n")
    
    # ONLY WORDS MODE
    use_words = True
    use_scrambled = False
    print("✅ Using WORDS ONLY mode\n")
    
    # Get speed configuration
    speed = args.speed if args.speed else 1000  # Increased default speed
    threads = args.threads if args.threads else min(speed * 4, 3000)
    delay = max(0.00001, 0.1 / speed)  # Reduced delay
    
    # Load proxies
    use_proxies = not args.no_proxies
    
    if not use_proxies:
        print("\n" + "=" * 70)
        print("⚠️  CRITICAL WARNING: PROXY PROTECTION DISABLED!")
        print("=" * 70)
        response = input("Type 'USE MY IP' to continue without proxies: ")
        if response.strip() != "USE MY IP":
            print("\n✅ Smart choice! Add proxies to proxies.txt")
            return
    
    if use_proxies:
        proxies = load_proxies(args.proxies)
        if not proxies:
            print("\n❌ ERROR: No proxies loaded!")
            print("   Create 'proxies.txt' with your proxy list.")
            return
        
        for proxy in proxies:
            proxy_queue.put(proxy)
        print(f"🛡️  IP PROTECTION: ENABLED ({len(proxies)} proxies loaded)\n")
    else:
        print("⚠️  IP PROTECTION: DISABLED\n")
    
    # Generate usernames
    combos = []
    count = args.count if args.count else 10000
    
    if use_scrambled:
        scrambled = generate_random_combos(lengths, count)
        combos.extend(scrambled)
        print(f"✅ Generated {len(scrambled):,} scrambled combinations\n")
    
    if use_words:
        words = load_word_list(lengths)
        if args.count and use_scrambled:
            words = words[:count // 2]
        elif args.count:
            words = words[:count]
        combos.extend(words)
        print(f"✅ Added {len(words):,} real words\n")
    
    random.shuffle(combos)
    print(f"📊 Total usernames to check: {len(combos):,}\n")
    
    # Create output files
    output_files = []
    for length in lengths:
        filename = f"{length}letter_telegram.txt"
        output_files.append(filename)
        with open(filename, "w", encoding="utf-8") as f:
            f.write(f"# Telegram Username Checker - Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"# Checking {length}-character usernames\n")
            f.write(f"# Format: username | full_url | timestamp\n")
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
    
    print(f"🚀 Starting username check with {threads} threads...")
    print(f"   Total usernames: {len(combos):,}")
    print(f"   Target speed: ~{speed} checks/second")
    print(f"   Estimated time: {len(combos) / speed / 60:.2f} minutes\n")
    
    # Progress bar
    with tqdm(total=len(combos), desc="Checking", unit="username") as pbar:
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = []
            
            for username in combos:
                future = executor.submit(worker, username, delay, stats, pbar, use_proxies)
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
    print(f"\n✅ Available usernames saved to:")
    for filename in output_files:
        print(f"   - {filename}")
    print("=" * 70 + "\n")
    
    # Keep window open
    input("Press Enter to exit...")


if __name__ == "__main__":
    main()
