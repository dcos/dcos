#!/usr/bin/env python
import json
import os
import base64
import requests

requests.packages.urllib3.disable_warnings()

#
# From : https://github.com/dcos/dcos/blob/master/test_util/helpers.py#L35
#
# Token valid until 2036 for user albert@bekstil.net
#    {
#        "email": "albert@bekstil.net",
#        "email_verified": true,
#        "iss": "https://dcos.auth0.com/",
#        "sub": "google-oauth2|109964499011108905050",
#        "aud": "3yF5TOSzdlI45Q1xspxzeoGBe9fNxm9m",
#        "exp": 2090884974,
#        "iat": 1460164974
#    }
#
credentials = {
  'token': 'eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiIsImtpZCI6Ik9UQkVOakZFTWtWQ09VRTRPRVpGTlRNMFJrWXlRa015Tnprd1JrSkVRemRCTWpBM1FqYzVOZyJ9.eyJlbWFpbCI6ImFsYmVydEBiZWtzdGlsLm5ldCIsImVtYWlsX3ZlcmlmaWVkIjp0cnVlLCJpc3MiOiJodHRwczovL2Rjb3MuYXV0aDAuY29tLyIsInN1YiI6Imdvb2dsZS1vYXV0aDJ8MTA5OTY0NDk5MDExMTA4OTA1MDUwIiwiYXVkIjoiM3lGNVRPU3pkbEk0NVExeHNweHplb0dCZTlmTnhtOW0iLCJleHAiOjIwOTA4ODQ5NzQsImlhdCI6MTQ2MDE2NDk3NH0.OxcoJJp06L1z2_41_p65FriEGkPzwFB_0pA9ULCvwvzJ8pJXw9hLbmsx-23aY2f-ydwJ7LSibL9i5NbQSR2riJWTcW4N7tLLCCMeFXKEK4hErN2hyxz71Fl765EjQSO5KD1A-HsOPr3ZZPoGTBjE0-EFtmXkSlHb1T2zd0Z8T5Z2-q96WkFoT6PiEdbrDA-e47LKtRmqsddnPZnp0xmMQdTr2MjpVgvqG7TlRvxDcYc-62rkwQXDNSWsW61FcKfQ-TRIZSf2GS9F9esDF4b5tRtrXcBNaorYa9ql0XAWH5W_ct4ylRNl3vwkYKWa4cmPvOqT5Wlj9Tf0af4lNO40PQ'
}

# Try to login
response = requests.post('%s/acs/api/v1/auth/login' % os.environ['CLUSTER_URL'], json=credentials, verify=False)

# Echo results
print(json.dumps({
  'token': response.json()['token'],
  'profile': {
    'uid': 'albert@bekstil.net',
    'description': 'albert'
  }
}))
