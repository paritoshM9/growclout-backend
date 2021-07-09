from flask import Flask, request, jsonify
from flask_cors import CORS
from deta import app, Deta
import datetime, pytz
import logging
import time
import requests
import os

DETA_KEY = os.environ.get("DETA_KEY")

deta = Deta(DETA_KEY)
db_users = deta.Base("users")
db_records = deta.Base("user_records")

app = Flask(__name__)
cors = CORS(app)

def has_public_access(user):
    user_generator_obj = db_users.fetch({"username": user})
    for user in user_generator_obj:
        return user[0]["public_access"]
    console.log("User doesnt exist")
    return False

def form_error_response():
    error_response = {
    "status_code" : 400,
    "message" : "Either user not found or public access is disabled for the requestor/user"
    }
    return jsonify(error_response, 400)

def is_public_access_available(user, requestor):
    if (requestor != user and (has_public_access(user) == False or has_public_access(requestor) == False)):
        return False
    return True

def fetch_user_record_data(user, data_type):
    t1 = time.time()
    records = db_records.fetch()
    tstamp_list = []
    result_data_list = []
    data_indices = {
    "followers" : 2,
    "marketcap" : 1,
    "coinprice" : 0
     }
    for record_list in records:
        record_list.sort(key=lambda x: x["timestamp"])
        for record in record_list:
            tstamp = record["timestamp"]
            if (user in record["values"]):
                values = record["values"][user]
                tstamp_list.append(tstamp)
                result_data_list.append(values[data_indices[data_type]])

    response = {
    "user" : user,
    "tstamp_list" : tstamp_list,
    "data": result_data_list
    }
    logging.error("Time taken to fetch: " + str(time.time() - t1))
    return jsonify(response, 200)

@app.route('/enable', methods=["POST"])
def enable_user():
    username = request.json.get("username")
    username = username.lower()
    key = request.headers.get("key")
    logging.error("key is: " + key)
    try:
        user = db_users.get(key)
        logging.error(user)
        if (user and user["username"] == username):
            logging.error("inside update")
            user["public_access"] = True
            user_updated = db_users.put(user)
            return jsonify({"message": "User updated successfully"}, 200)
        else:
            return jsonify({"message": "User authentication failed"}, 403)

    except:
        return jsonify({"message": "User not found"}, 400)

@app.route('/users/<key>', methods = ["GET"])
def get_user(key):
    key = key.lower()
    try:
        user_generator_obj = db_users.fetch({"username": key})
        for user in user_generator_obj:
            resp_user = {}
            resp_user["username"] = user[0]["username"]
            resp_user["public_access"] = user[0]["public_access"]
            return jsonify(resp_user, 200)
    except:
        return jsonify({"error": "Not found"}, 404)

@app.route('/users/<key>', methods = ["DELETE"])
def delete_user(key):
    key = key.lower()
    userkey = request.headers.get("key")
    logging.error("User key is: " + userkey)
    try:
        user = db_users.get(userkey)
        logging.error(user)
        if (user and user["username"] == key):
            db_users.delete(userkey)
            return jsonify({"user": key, "message": "Deleted Successfully"}, 200)
        else:
            return jsonify({"error": "Authentication Failed"}, 403)
    except:
        return jsonify({"error": "Error While Deleting"}, 400)


@app.route('/register', methods=["POST"])
def create_user():
    username = request.json.get("username")
    username = username.lower()
    public_access = request.json.get("public_access")
    current_time = datetime.datetime.utcnow().isoformat()
    try:
        user_if_present = db_users.fetch({"username": username})
        for user in user_if_present:

            if (len(user) > 0 ):
                logging.error("user already present: ")
                logging.error(user[0])
                return jsonify(user[0], 201)

        user = db_users.put({
            "username": username,
            "public_access": public_access,
            "registered_at": current_time,
            "last_updated": ""
        })
        logging.error("calling update stats")
        update_stats(username, user)
        return jsonify(user, 201)

    except:
        user = db_users.put({
            "username": username,
            "public_access": public_access,
            "registered_at": current_time,
            "last_updated": ""
        })
        logging.error("exception : calling update stats")

        update_stats(username, user)

        return jsonify(user, 201)


@app.route('/followers', methods=["GET"])
def get_follower_data_last_30_days():
    requestor = request.args.get('requestor')
    requestor = requestor.lower()
    user = request.args.get('user')
    user = user.lower()

    if (is_public_access_available(user, requestor) == False):
        return form_error_response()

    else:
        return fetch_user_record_data(user, "followers")

@app.route('/coinprice', methods=["GET"])
def get_coin_prices_last_30_days():
    requestor = request.args.get('requestor')
    requestor = requestor.lower()
    user = request.args.get('user')
    user = user.lower()

    if (is_public_access_available(user, requestor) == False):
        return form_error_response()

    else:
        return fetch_user_record_data(user, "coinprice")

@app.route('/marketcap', methods=["GET"])
def get_market_cap_last_30_days():
    requestor = request.args.get('requestor')
    requestor = requestor.lower()
    user = request.args.get('user')
    user = user.lower()

    if (is_public_access_available(user, requestor) == False):
        return form_error_response()

    else:
        return fetch_user_record_data(user, "marketcap")


"""

Cron Job Functions. Triggered when new user is created

"""

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
        logging.error(response)
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
        logging.error("Proof for new deployment" + user)

        return followers_count
    except:
        logging.error("Exception occured while fetching followers data of user " + user)
        return -1

def fetch_users_from_db():
    users = []
    users_json = db_users.fetch()
    for user_list in users_json:
        for item in user_list:
            username = item["username"]
            logging.error(username)
            users.append(username)
    return users

def update_stats(newuser, user_json):
    logging.warning("Updating Stats since new user is added")
    t1 = time.time()
    # users = fetch_users_from_db()
    users = [newuser]
    if (len(users) == 0):
        return "No users found"

    #tstamp = datetime.datetime.utcnow().isoformat()
    tz = pytz.timezone("UTC")
    tstamp = datetime.datetime.now(tz).isoformat()
    logging.warning(tstamp)

    records = {}
    for user in users:

        user_stats = [] #cp, mc, followers
        coin_price, market_cap = get_profile_values(user)
        followers_count = get_follower_counts(user)
        if (coin_price == -1 or market_cap == -1 or followers_count == -1):
            continue
        else:
            user_stats.append(coin_price)
            user_stats.append(market_cap)
            user_stats.append(followers_count)
            records[user] = user_stats

    new_record = {}
    new_record["timestamp"] = tstamp
    new_record["values"] = records
    # adding data to the user_records
    db_records.put(new_record)

    # updating users last updated field
    current_time = time.time()
    logging.error("Updating last processed time of user " + newuser + " to " + str(current_time))
    user_json["last_updated"] = int(current_time)
    user_updated = db_users.put(user_json)


    logging.error("Time taken by cron job: " + str(time.time() - t1))
    return "new db updated correctly"
