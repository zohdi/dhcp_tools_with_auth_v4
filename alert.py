import subprocess

REMOTE_HOST = "zmahamee@asic-vm-sjc1117"
REMOTE_FILE = "/tmp/send_mail_alert.py"

# The content of the remote script
MAILGUN_SCRIPT = """import os
import requests

def send_simple_message():
    return requests.post(
        "https://api.mailgun.net/v3/sandbox0c9c22d880f74ae1a011ffab6586542f.mailgun.org/messages",
        auth=("api", os.getenv('API_KEY', '50d8352acf1cee4c7dc9576599d39ec1-67edcffb-677decfa')),
        data={"from": "Mailgun Sandbox <postmaster@sandbox0c9c22d880f74ae1a011ffab6586542f.mailgun.org>",
              "to": "Zohdi Mahameed <zmahamee@cisco.com>",
              "subject": "From DHCP SJC Server - 172.24.78.53 - DHCP Web Manager Alert",
              "text": "DHCP Web Service is DOWN! please check immediately!! IP 172.24.78.53"})

response = send_simple_message()
print("Status:", response.status_code, response.text)
"""

# Check if the file exists on remote host
check_cmd = f"ssh {REMOTE_HOST} 'test -f {REMOTE_FILE} && echo exists || echo missing'"
result = subprocess.run(check_cmd, shell=True, capture_output=True, text=True)
if "missing" in result.stdout:
    # Write the script remotely
    write_cmd = f"ssh {REMOTE_HOST} 'cat > {REMOTE_FILE}'"
    proc = subprocess.Popen(write_cmd, shell=True, stdin=subprocess.PIPE)
    proc.communicate(input=MAILGUN_SCRIPT.encode())

    print("Remote script created.")

# Execute the remote script
run_cmd = f"ssh {REMOTE_HOST} 'python3 {REMOTE_FILE}'"
subprocess.run(run_cmd, shell=True)

