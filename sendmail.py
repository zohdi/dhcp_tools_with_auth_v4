import os
import requests
def send_simple_message():
  	return requests.post(
  		"https://api.mailgun.net/v3/sandbox0c9c22d880f74ae1a011ffab6586542f.mailgun.org/messages",
  		auth=("api", os.getenv('API_KEY', 'API_KEY')),
  		data={"from": "Mailgun Sandbox <postmaster@sandbox0c9c22d880f74ae1a011ffab6586542f.mailgun.org>",
			"to": "Zohdi Mahameed <zmahamee@cisco.com>",
  			"subject": "Hello Zohdi Mahameed",
  			"text": "DHCP Web Service is DOWN! please check immediately!!"})
