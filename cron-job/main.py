from deta import app, Deta
import requests
import datetime, pytz
import logging
import time
import os

DETA_KEY = os.environ.get("DETA_KEY")

deta = Deta(DETA_KEY)
db_users = deta.Base("users")
db_records = deta.Base("user_records")

batch_size = 5
interval_in_minutes = 60
cron_frequency = 5 #just for reference


def get_btc_value():
    api = "https://bitclout.com/api/v0/get-exchange-rate"
    response = requests.get(api)
    response_json = response.json()
    usd_rate = response_json["USDCentsPerBitCloutExchangeRate"]/100
    return usd_rate

def nano_btc_to_dollars(nano_btc):
    btc_value = get_btc_value()
    dollar_price = (nano_btc)*btc_value/10e8
    return dollar_price

def get_profile_values(user):
    profile_details_api = "https://bitclout.com/api/v0/get-single-profile"
    payload_profile = {"PublicKeyBase58Check":"","Username":""}
    payload_profile["Username"] = user
    logging.error("Fetching profile data of user "+ user)
    try:
        response = requests.post(profile_details_api, json = payload_profile).json()
        coin_price_nano_btc = response["Profile"]["CoinPriceBitCloutNanos"]
        coin_price_dollars = nano_btc_to_dollars(coin_price_nano_btc)
        market_cap_dollars = (response["Profile"]["CoinEntry"]["CoinsInCirculationNanos"]/10e8)*coin_price_dollars
        return [coin_price_dollars, market_cap_dollars]
    except:
        logging.error("Exception occured while fetching profile data of user " + user)
        return [-1, -1]

def get_follower_counts(user):
    follower_details_api = "https://bitclout.com/api/v0/get-follows-stateless"
    payload_follower = {"Username":"","PublicKeyBase58Check":"","GetEntriesFollowingUsername":True,"LastPublicKeyBase58Check":"","NumToFetch":1}
    payload_follower["Username"] = user
    logging.error("Fetching followers data of user "+ user)
    try:
        response = requests.post(follower_details_api, json = payload_follower).json()
        followers_count = response["NumFollowers"]

        return followers_count
    except:
        logging.error("Exception occured while fetching followers data of user " + user)
        return -1

def fetch_users_from_db():
    users = []
    users_json = db_users.fetch()
    for user_list in users_json:

        # sorting users based on last_updated
        user_list.sort(key=lambda x: int(x["last_updated"]))
        running_batch_size = 0
        current_time = time.time()

        for item in user_list:
            user_last_updated = float(item["last_updated"])
            time_diff_in_minutes = (current_time - user_last_updated)/60 #minutes
            if (time_diff_in_minutes > interval_in_minutes):
                username = item["username"]
                logging.error("User selected: " + username + " for batch with current_time: " + str(current_time) + " with last_updated: " + str(user_last_updated))
                logging.error("Time time_diff_in_minutes: " + str(time_diff_in_minutes))
                users.append(item)
                running_batch_size += 1
            if (running_batch_size >= batch_size):
                break
    return users


def update_last_updated(user, current_time):
    # current_time = int(time.time())
    logging.error("Updating last processed time of user " + user["username"] + " to " + str(current_time))
    user["last_updated"] = current_time
    user_updated = db_users.put(user)


@app.lib.cron()
def update_stats(event):
    t1 = time.time()
    users = fetch_users_from_db()
    if (len(users) == 0):
        return "No user to be updated in this cycle"

    #tstamp = datetime.datetime.utcnow().isoformat()
    tz = pytz.timezone("UTC")
    tstamp = datetime.datetime.now(tz).isoformat()
    logging.warning(tstamp)

    records = {}
    for user in users:

        user_stats = [] #cp, mc, followers
        coin_price, market_cap = get_profile_values(user["username"])
        followers_count = get_follower_counts(user["username"])
        if (coin_price == -1 or market_cap == -1 or followers_count == -1):
            continue
        else:
            user_stats.append(coin_price)
            user_stats.append(market_cap)
            user_stats.append(followers_count)
            records[user["username"]] = user_stats
            # update_last_updated(user, current_time)

    new_record = {}
    new_record["timestamp"] = tstamp
    new_record["values"] = records

    db_records.put(new_record)
    logging.error("Batch updated")
    current_time = int(time.time()) # used to update the last updated

    summary = "User records updated for "
    for user in users:
        if (user["username"] in new_record["values"]):
            update_last_updated(user, current_time)
            summary = summary + user["username"] + ", "
    summary = summary + " in time : " + str(time.time() - t1)
    logging.error("Time taken by cron job: " + str(time.time() - t1))
    return summary
