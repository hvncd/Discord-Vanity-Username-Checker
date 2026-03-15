#!/usr/bin/env python3
"""
Discord Username Checker - FAST & RANDOMIZED
=============================================
Scans random 3-letter and 4-letter usernames (a-z, 0-9) to find available Discord usernames.

WARNING: This script may violate Discord's Terms of Service.
- Using your token for automated requests risks account termination
- Username changes have strict rate limits and cooldowns
- Mass checking may result in instant ban
- USE AT YOUR OWN RISK

Installation:
    pip install requests tqdm

Usage:
    python discord_username_checker.py --token YOUR_DISCORD_TOKEN
    python discord_username_checker.py --token YOUR_TOKEN --threads 50 --delay 0.1
"""

import argparse
import itertools
import json
import time
import random
from datetime import datetime
from typing import List, Set
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from queue import Queue

import requests
from tqdm import tqdm


# Discord API Configuration
DISCORD_API_BASE = "https://discord.com/api/v9"
USER_ENDPOINT = f"{DISCORD_API_BASE}/users/@me"

# Thread-safe file writing and proxy rotation
file_lock = Lock()
stats_lock = Lock()
proxy_queue = Queue()


def load_proxies(proxy_file: str = "proxies.txt") -> List[str]:
    """Load SOCKS4 proxies from file."""
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


def get_tokens_interactive() -> List[str]:
    """
    Prompt user to enter Discord tokens interactively.
    
    Returns:
        List of Discord tokens
    """
    print("\n" + "=" * 70)
    print("🔑 DISCORD TOKEN INPUT")
    print("=" * 70)
    print("Enter your Discord token(s). Multiple tokens help avoid rate limits.")
    print("Each token should be on a separate line.")
    print("Press Enter twice (empty line) when done.\n")
    
    tokens = []
    token_num = 1
    
    while True:
        token = input(f"Token #{token_num} (or press Enter to finish): ").strip()
        if not token:
            if tokens:
                break
            else:
                print("⚠️  You must enter at least one token!")
                continue
        
        # Basic validation
        if len(token) < 50:
            print("⚠️  That doesn't look like a valid Discord token (too short)")
            continue
        
        tokens.append(token)
        print(f"✅ Token #{token_num} added")
        token_num += 1
    
    print(f"\n✅ Total tokens loaded: {len(tokens)}")
    print("=" * 70 + "\n")
    return tokens


def get_speed_interactive(num_tokens: int) -> tuple[int, float]:
    """
    Prompt user to set target requests per second.
    
    Args:
        num_tokens: Number of tokens being used
    
    Returns:
        Tuple of (threads, delay)
    """
    print("\n" + "=" * 70)
    print("⚡ SPEED CONFIGURATION")
    print("=" * 70)
    print("Set how many usernames to check per second.")
    print()
    print("Recommendations:")
    print(f"  • With {num_tokens} token(s):")
    if num_tokens == 1:
        print("    - Safe: 1-5 checks/second (low ban risk)")
        print("    - Moderate: 10-20 checks/second (medium risk)")
        print("    - Fast: 50+ checks/second (HIGH RISK)")
    elif num_tokens <= 5:
        print("    - Safe: 10-25 checks/second")
        print("    - Moderate: 50-100 checks/second")
        print("    - Fast: 150+ checks/second (some risk)")
    else:
        print("    - Safe: 50-100 checks/second")
        print("    - Moderate: 150-300 checks/second")
        print("    - Fast: 500-2000 checks/second (TURBO MODE)")
        print("    - INSANE: 5000+ checks/second (MAXIMUM RISK)")
    print()
    print("⚠️  Higher speed = faster checking but HIGHER ban risk!")
    print("=" * 70 + "\n")
    
    while True:
        speed_input = input("Enter checks per second (e.g., 50): ").strip()
        
        if not speed_input:
            default_speed = 50 if num_tokens > 1 else 5
            print(f"Using default: {default_speed} checks/second")
            threads = min(default_speed * 2, 200)
            delay = max(0.01, 1.0 / default_speed)
            return threads, delay
        
        try:
            speed = int(speed_input)
            if speed <= 0:
                print("⚠️  Speed must be positive!")
                continue
            
            if speed > 1000:
                print("⚠️  Speed over 1000/sec is extremely risky!")
                confirm = input("Continue anyway? (yes/no): ").strip().lower()
                if confirm != "yes":
                    continue
            
            # Calculate optimal threads and delay
            # For MAXIMUM SPEED: 3x threads to handle latency
            threads = min(speed * 3, 2000)
            delay = max(0.0001, 0.5 / speed)
            
            print(f"✅ Speed set to: {speed} checks/second")
            print(f"   Using {threads} threads with {delay:.4f}s delay")
            print(f"   ⚡ TURBO MODE ENABLED\n")
            return threads, delay
        
        except ValueError:
            print("⚠️  Invalid number! Please enter an integer like 50")
            continue


def print_warning():
    """Display important warnings before execution."""
    print("\n" + "=" * 70)
    print("⚠️  CRITICAL WARNING ⚠️")
    print("=" * 70)
    print("This script may VIOLATE Discord's Terms of Service!")
    print()
    print("Risks:")
    print("  • Using your token for automation may result in ACCOUNT TERMINATION")
    print("  • Username changes have strict rate limits and cooldowns")
    print("  • Mass checking can trigger instant bans")
    print("  • Discord actively monitors for automated behavior")
    print()
    print("By continuing, you accept ALL RISKS and consequences.")
    print("=" * 70 + "\n")
    
    response = input("Type 'I UNDERSTAND' to continue: ")
    if response.strip() != "I UNDERSTAND":
        print("\n❌ Aborted by user.")
        exit(0)
    print()


def generate_random_combos(lengths: List[int], count: int = None) -> List[str]:
    """
    Generate RANDOMIZED username combinations for given lengths.
    
    Args:
        lengths: List of username lengths to generate (e.g., [3, 4])
        count: Number of random combinations to generate (None = 10000 default)
    
    Returns:
        List of randomized username combinations
    """
    characters = "abcdefghijklmnopqrstuvwxyz0123456789"
    combos = []
    
    print("🔄 Generating RANDOMIZED username combinations...")
    
    if count is None:
        count = 10000  # Default to 10k random combos
    
    # Generate random combinations
    seen = set()
    for length in lengths:
        length_count = count // len(lengths)
        while len([c for c in combos if len(c) == length]) < length_count:
            username = ''.join(random.choices(characters, k=length))
            if username not in seen:
                seen.add(username)
                combos.append(username)
    
    return combos


def load_word_list(lengths: List[int]) -> List[str]:
    """
    Load real English words for username checking.
    
    Args:
        lengths: List of word lengths to include (e.g., [3, 4])
    
    Returns:
        List of words to check
    """
    length_str = ", ".join(map(str, lengths))
    print(f"📚 Loading REAL word list ({length_str} character words)...")
    
    all_words = set()
    
    # Use Google's most common words (real words people actually use)
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
        print(f"   ✓ Loaded {len(all_words):,} REAL common words")
    except Exception as e:
        print(f"   ⚠️ Failed to load online list: {e}")
    
    # Add more common words from another source
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
        print(f"   ✓ Total REAL words: {len(all_words):,}")
    except:
        pass
    
    if all_words:
        word_list = list(all_words)
        random.shuffle(word_list)
        return word_list
    
    # Fallback words
    print(f"   Using fallback words...")
    fallback = {
        3: ["ace", "aim", "air", "art", "bad", "ban", "bar", "bat", "bay", "bed",
            "bet", "big", "bit", "box", "boy", "bug", "bus", "buy", "car", "cat"],
        4: ["cool", "epic", "game", "play", "chat", "talk", "best", "fire", "hype",
            "vibe", "zone", "team", "clan", "crew", "gang", "wild", "dope", "sick"],
        5: ["elite", "squad", "guild", "chill", "place", "space", "cyber", "hyper",
            "super", "ultra", "mega", "omega", "alpha", "delta", "sigma", "prime"]
    }
    
    result = []
    for length in lengths:
        if length in fallback:
            result.extend(fallback[length])
    
    random.shuffle(result)
    return result


def check_username(username: str, session: requests.Session, proxy_str: str) -> tuple[bool, str]:
    """
    Check if a username is available on Discord - NO TOKEN NEEDED.
    Uses Discord's public unique username endpoint.
    
    Args:
        username: The username to check
        session: Requests session
        proxy_str: Specific proxy to use for this request
    
    Returns:
        Tuple of (is_available, status_message)
    """
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    }
    
    # Use the assigned proxy
    proxies = {"http": proxy_str, "https": proxy_str}
    
    try:
        # Check username availability using public endpoint
        check_url = f"{DISCORD_API_BASE}/unique-username/username-attempt-unauthed"
        payload = {"username": username}
        
        response = session.post(check_url, json=payload, headers=headers, proxies=proxies, timeout=10.0)
        
        if response.status_code == 200:
            data = response.json()
            # Check if username is taken
            taken = data.get("taken", True)
            if taken:
                return False, "taken"
            else:
                return True, "available"
        
        elif response.status_code == 429:
            return False, "rate_limited"
        
        else:
            return False, "error"
    
    except requests.exceptions.ProxyError:
        return False, "proxy_error"
    except requests.exceptions.Timeout:
        return False, "timeout"
    except requests.exceptions.RequestException:
        return False, "network_error"
        
        # Unauthorized - invalid token
        if response.status_code == 401:
            return False, "invalid_token", True
        
        # Other errors
        return False, "error", False
    
    except requests.exceptions.ProxyError:
        # Bad proxy, don't return to queue
        return False, "proxy_error", False
    except requests.exceptions.Timeout:
        # Timeout - don't return slow proxy
        return False, "timeout", False
    except requests.exceptions.RequestException:
        # Network error - don't return bad proxy
        return False, "network_error", False


def save_available_username(username: str, filename: str = "available_usernames.txt"):
    """
    Thread-safe INSTANT save of available username to file with timestamp.
    Flushes immediately so data is written even if script crashes.
    
    Args:
        username: The available username
        filename: Output file path
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with file_lock:
        with open(filename, "a", encoding="utf-8") as f:
            f.write(f"{username} | {timestamp}\n")
            f.flush()  # Force immediate write to disk


def worker(username: str, proxy_str: str, delay: float, stats: dict, pbar: tqdm) -> None:
    """Worker function - each thread gets its own dedicated proxy."""
    session = requests.Session()
    session.trust_env = False
    
    is_available, status = check_username(username, session, proxy_str)
    
    # Only retry once on network errors
    if status in ["network_error", "timeout"]:
        is_available, status = check_username(username, session, proxy_str)
    
    with stats_lock:
        stats['total_checked'] += 1
        
        if is_available:
            stats['available_count'] += 1
            save_available_username(username)
            tqdm.write(f"✅ AVAILABLE: {username}")
        elif status == "taken":
            stats['taken_count'] += 1
            tqdm.write(f"   {username} - taken")
        elif "rate_limited" in status:
            stats['rate_limit_count'] += 1
            tqdm.write(f"⏳ {username} - rate limited")
        elif status in ["timeout", "proxy_error", "network_error"]:
            stats['error_count'] += 1
            # Show occasional error messages
            if stats['error_count'] % 100 == 1:
                tqdm.write(f"⚠️  Many proxy errors - proxies may be slow/dead")
        else:
            stats['error_count'] += 1
        
        pbar.update(1)
        pbar.set_postfix({
            "Available": stats['available_count'],
            "Taken": stats['taken_count'],
            "RateLimits": stats['rate_limit_count']
        })
    
    # Delay between requests
    time.sleep(delay)


def main():
    """Main execution function."""
    parser = argparse.ArgumentParser(
        description="Discord Username Availability Checker - FAST & RANDOMIZED",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )
    
    parser.add_argument(
        "--token",
        help="Discord user token (will prompt if not provided)"
    )
    
    parser.add_argument(
        "--tokens",
        help="Multiple tokens separated by commas (for rate limit distribution)"
    )
    
    parser.add_argument(
        "--lengths",
        default=None,
        help="Comma-separated list of username lengths to check (e.g., 3,4)"
    )
    
    parser.add_argument(
        "--speed",
        type=int,
        default=None,
        help="Target checks per second (e.g., 50, 100, 200)"
    )
    
    parser.add_argument(
        "--delay",
        type=float,
        default=None,
        help="[LEGACY] Delay in seconds between checks per thread"
    )
    
    parser.add_argument(
        "--threads",
        type=int,
        default=None,
        help="Number of concurrent threads (auto-calculated from speed if not provided)"
    )
    
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help="Number of random usernames to check (default: all possible)"
    )
    
    parser.add_argument(
        "--proxies",
        default="proxies.txt",
        help="Path to proxy list file (one per line, format: ip:port)"
    )
    
    parser.add_argument(
        "--no-proxies",
        action="store_true",
        help="Disable proxy usage"
    )
    
    parser.add_argument(
        "--skip-warning",
        action="store_true",
        help="Skip the warning prompt (use with caution)"
    )
    
    args = parser.parse_args()
    
    print("\n" + "=" * 70)
    print("Discord Username Checker - NO TOKEN REQUIRED")
    print("=" * 70)
    print("This script checks username availability using ONLY proxies.")
    print("No Discord authentication needed!")
    print("=" * 70 + "\n")
    
    # Parse or ask for username lengths
    if args.lengths:
        try:
            lengths = [int(x.strip()) for x in args.lengths.split(",")]
        except ValueError:
            print("❌ Error: --lengths must be comma-separated integers (e.g., 3,4)")
            return
    else:
        print("Choose username lengths to check:")
        print("  Examples: 3,4  or  3  or  3,4,5")
        print("  Recommended: 3,4 (most available)")
        lengths_input = input("\nEnter username lengths (comma-separated): ").strip()
        
        if not lengths_input:
            lengths = [3, 4]  # Default
            print(f"Using default: {lengths}")
        else:
            try:
                lengths = [int(x.strip()) for x in lengths_input.split(",")]
            except ValueError:
                print("❌ Error: Invalid input. Using default: 3,4")
                lengths = [3, 4]
    
    print(f"\n✅ Checking usernames with {', '.join(map(str, lengths))} characters\n")
    
    # Ask for generation mode
    print("Choose username generation mode:")
    print("  1. Scrambled only (random: a3x, k9z, 2b7)")
    print("  2. Words only (real words: cat, dog, ace)")
    print("  3. Both scrambled and words (mixed)")
    mode_input = input("\nEnter mode (1/2/3): ").strip()
    
    if mode_input == "2":
        use_words = True
        use_scrambled = False
        print("✅ Using WORDS only\n")
    elif mode_input == "3":
        use_words = True
        use_scrambled = True
        print("✅ Using BOTH words and scrambled\n")
    else:
        use_words = False
        use_scrambled = True
        print("✅ Using SCRAMBLED only\n")
    
    # Show warning
    if not args.skip_warning:
        print_warning()
    
    # Get speed configuration
    speed = args.speed if args.speed else 500
    threads = args.threads if args.threads else min(speed * 4, 3000)
    delay = max(0.00001, 0.3 / speed)
    
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
        
        print(f"🛡️  IP PROTECTION: ENABLED ({len(proxies)} proxies loaded)")
        print(f"   Your real IP will NOT be used")
        print(f"   Each proxy will be used simultaneously!\n")
        
        # Use ALL proxies - set threads to match proxy count
        threads = len(proxies)
        print(f"⚡ TURBO MODE: Using ALL {threads} proxies at once!\n")
    else:
        print("⚠️  IP PROTECTION: DISABLED (using your real IP - DANGEROUS!)\n")
        return
    
    # Generate combinations based on mode
    combos = []
    
    if use_scrambled:
        scrambled = generate_random_combos(lengths, args.count)
        combos.extend(scrambled)
        print(f"✅ Generated {len(scrambled):,} scrambled combinations\n")
    
    if use_words:
        words = load_word_list(lengths)
        if args.count and use_scrambled:
            # If we have a count and both modes, split it
            words = words[:args.count // 2]
        elif args.count:
            words = words[:args.count]
        combos.extend(words)
        print(f"✅ Added {len(words):,} real words\n")
    
    # Shuffle everything together
    random.shuffle(combos)
    print(f"📊 Total usernames to check: {len(combos):,}\n")
    
    # Create/clear the output file at start
    with open("available_usernames.txt", "w", encoding="utf-8") as f:
        f.write(f"# Discord Username Checker - Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"# Checking {len(combos):,} usernames\n")
        f.write(f"# Format: username | timestamp\n")
        f.write("#" + "=" * 67 + "\n\n")
        f.flush()
    
    print(f"📝 Output file created: available_usernames.txt")
    print(f"   Available usernames will be saved INSTANTLY as they're found!\n")
    
    # Statistics
    stats = {
        'total_checked': 0,
        'available_count': 0,
        'taken_count': 0,
        'error_count': 0,
        'rate_limit_count': 0
    }
    
    print(f"🚀 Starting MAXIMUM SPEED username check with {threads} threads...")
    print(f"   Total usernames: {len(combos):,}")
    print(f"   Using ALL {len(proxies)} proxies simultaneously!")
    print(f"   Each proxy will hammer Discord until rate limited!")
    print(f"   Estimated time: {len(combos) / threads / 60:.2f} minutes\n")
    
    # Progress bar
    with tqdm(total=len(combos), desc="Checking", unit="username") as pbar:
        with ThreadPoolExecutor(max_workers=threads) as executor:
            futures = []
            
            # Assign usernames to proxies in round-robin fashion
            for i, username in enumerate(combos):
                proxy = proxies[i % len(proxies)]  # Cycle through all proxies
                future = executor.submit(worker, username, proxy, delay, stats, pbar)
                futures.append(future)
            
            # Wait for all to complete
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
    
    print(f"\n✅ Available usernames saved to: available_usernames.txt")
    print("=" * 70 + "\n")
    
    # Keep window open
    input("Press Enter to exit...")


if __name__ == "__main__":
    main()
