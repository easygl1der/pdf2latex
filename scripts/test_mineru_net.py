import requests
import sys
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).parent.parent))

from scripts.mineru_convert import MinerUConverter
from scripts.config import MINERU_API_KEY

def test_mineru_connectivity():
    print("Testing MinerU API connectivity (Direct Connection)...")
    print(f"Token: {MINERU_API_KEY[:5]}...{MINERU_API_KEY[-5:]}")
    
    converter = MinerUConverter(MINERU_API_KEY)
    
    # Try a simple GET request to the batch status endpoint (even with a fake ID)
    # to see if the network connection is successful.
    fake_batch_id = "test_connectivity_id"
    url = f"https://mineru.net/api/v4/extract-results/batch/{fake_batch_id}"
    
    print(f"Connecting to: {url}")
    print(f"Using proxies: {converter.session.proxies}")
    
    try:
        response = converter.session.get(
            url, 
            timeout=10
        )
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.text[:200]}")
        
        if response.status_code in [200, 404]: # 404 is expected for fake ID, but means we reached the server
            print("\n✅ Connectivity test successful! The server is reachable.")
        else:
            print(f"\n⚠️ Unexpected status code: {response.status_code}")
            
    except requests.exceptions.ProxyError as e:
        print(f"\n❌ Proxy Error: {e}")
    except requests.exceptions.ConnectionError as e:
        print(f"\n❌ Connection Error: {e}")
    except Exception as e:
        print(f"\n❌ Unexpected Error: {type(e).__name__}: {e}")

if __name__ == "__main__":
    test_mineru_connectivity()
