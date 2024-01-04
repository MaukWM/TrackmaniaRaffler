import json
import sys
import time
import numpy as np
import config

import requests
from tqdm import tqdm

headers = {
    "User-Agent": "Campaign raffler / Discord: @dawarfmaster / maukmul@gmail.com",
    "content-type": "application/json"
}

# # --------------------
# # Make an access token somehow
# url = 'https://public-ubiservices.ubi.com/v3/profiles/sessions'
# myobj = {'Content-Type': 'application/json', 'Ubi-AppId': '86263886-327a-4328-ac69-527f0d20a237', 'Authorization': 'Basic aGpqeGd0Ym56dmF0cGV4cW9rQGNrcHRyLmNvbTpuRU0zMDN3YCFPMw==', 'User-Agent': "Campaign raffler / Discord: @dawarfmaster / maukmul@gmail.com"}
#
# s = requests.Session()
# x = s.post(url, headers=myobj)
#
# data_token = x.json()
# token = data_token["ticket"]
#
# url = 'https://prod.trackmania.core.nadeo.online/v2/authentication/token/ubiservices'
# myobj = {'Content-Type': 'application/json', 'Authorization': 'ubi_v1 t=' + token}
#
# x = s.post(url, headers=myobj, json={"audience":"NadeoLiveServices"})
#
# data_accessToken = x.json()
# accessToken = data_accessToken["accessToken"]
# # ------------------

# API endpoint for access token
token_url = "https://api.trackmania.com/api/access_token"

# Data to be sent in the request body
data = {
    "grant_type": "client_credentials",
    "client_id": config.client_id,
    "client_secret": config.client_secret
}

# Make the POST request
response = requests.post(token_url, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})

# Check the response status
if response.status_code == 200:
    # Successful request
    access_token = response.json().get("access_token")
    print("Access Token:", access_token)
else:
    # Print error details for unsuccessful requests
    print(f"Error: {response.status_code}, {response.text}")
    sys.exit(0)


def retrieve_campaign_data(campaign_id):
    """
    Given a campaign id. Retrieve basic data surrounding it (maps, map author, times, map ids, etc.). This can be used later for determining tickets.
    :param campaign_id: Id of the campaign. Taking from "https://trackmania.io/#/campaigns/35145/50013" the id would be "35145/50013"
    :return: Retrieved data
    """
    api_url = f"https://trackmania.io/api/campaign/{campaign_id}"

    response = requests.get(api_url, headers=headers)

    if response.status_code == 200:
        data = response.json()

        # Write the JSON data to a file
        with open(f"{data['name']}.json", "w") as file:
            json.dump(data, file, indent=4)

        print(f"JSON data written to {data['name']}.json")
        return data
    else:
        print(f"Error: {response.status_code}")


def retrieve_map_data(map_name, leaderboard_uid, map_uid):
    api_url = f"https://trackmania.io/api/leaderboard/{leaderboard_uid}/{map_uid}?offset=0&length=1000"

    response = requests.get(api_url, headers=headers)

    if response.status_code == 200:
        data = response.json()

        # Write the JSON data to a file
        with open(f"{map_name}.json", "w") as file:
            json.dump(data, file, indent=4)

        print(f"JSON data written to {map_name}.json")
    else:
        print(f"Error: {response.status_code}")


def extract_map_data(map_playlist):
    """
    Extract basic information needed to perform a raffle from campaign data.
    :param map_playlist: Map playlist extracted from campaign data
    :return: A list of tuples (mapUid, AT time, gold time, silver time, bronze time)
    """
    results = []
    for map in map_playlist:
        results.append((map['mapUid'], map['authorScore'], map['goldScore'], map['silverScore'], map['bronzeScore']))
    return results


def collect_records(map_list, max_leaderboard_depth=10):
    """
    Collect records for each map
    :param map_list: List of maps to extract
    :param max_leaderboard_depth: Max page depth to extract data from
    :return: Collected records
    """
    print("Collecting map records, this might take some time")
    pbar = tqdm(total=len(map_list))
    results = []
    for mapUid, _, _, _, _ in map_list:
        templist = []
        for i in range(max_leaderboard_depth):
            url = 'https://live-services.trackmania.nadeo.live/api/token/leaderboard/group/Personal_Best/map/' + mapUid + '/top?length=100&onlyWorld=true&offset=' + str(
                i * 100)
            x = requests.get(url, headers={'Authorization': 'nadeo_v1 t=' + accessToken})
            time.sleep(0.2)
            tempdict = json.loads(x.text)
            extracted_record_list = tempdict['tops'][0]['top']

            # If we aren't extracting any more records, simply move on to the next map.
            if len(extracted_record_list) == 0:
                break
            templist += extracted_record_list
        results.append(templist)
        pbar.update(1)

    # Write records to a json file so we don't have to spam the server every time we perform a raffle
    with open(f"records.json", "w") as file:
        json.dump(records, file, indent=4)

    return results


def collect_medal_occurences_per_map(map_list, records):
    """
    For the map list and records, collect the amount of occurences of each medal. This can be used later to determine
    rarity so that specific medals earn more tickets
    :param map_list: List of maps with time requirements for medals
    :param records: Records for each map
    :return: List of counters
    """
    counters = np.zeros((25, 4), dtype=np.int32)
    # Yes this line is ugly. No I won't change it
    holders = [[[], [], [], []] for _ in range(25)]

    for i in range(len(map_list)):
        medal_times = map_list[i][1:]
        current_map_records = records[i]
        for map_record in current_map_records:
            current_record_score = map_record['score']
            record_player = map_record['accountId']
            for j in range(len(medal_times)):
                current_medal_time = medal_times[j]
                if current_record_score < current_medal_time:
                    counters[i][j] += 1
                    holders[i][j].append(record_player)

    return counters, holders


def determine_tickets_per_map(counters):
    """
    Given a list of medal counters, determine how much tickets the AT of that map is worth.
    :param counters: List of medal counters. Shape (25, 4) (maps, medal_counts). With medals being [AT, gold, silver, bronze]
    :return: Amount of tickets for each map for each medal
    """
    for i, counter in enumerate(counters):
        print(f"{campaign_data['playlist'][i]['name']}: {counter}")

    # Get the indices that would sort the array based on the AT. This gives us the rarity of each AT.
    # TODO: Currently, maps with the same amount of ATs get a different ranking. It would be better to give them a shared place. Or resolve some other way
    sorted_indices = np.argsort(counters[:, 0])

    # Dish out ticket values for each maps AT rarity:
    AT_tickets = np.zeros(25, dtype=np.int32)
    temp_tickets = np.arange(25, 0, -1)
    for i, rarity_idx in enumerate(sorted_indices):
        AT_tickets[rarity_idx] = temp_tickets[i]

    # Golds are worth 1 ticket
    gold_tickets = np.ones(25, dtype=np.int32)

    # Silvers and bronzes are worth nothing
    silver_tickets = np.zeros(25, dtype=np.int32)
    bronze_tickets = np.zeros(25, dtype=np.int32)

    return np.stack([AT_tickets, gold_tickets, silver_tickets, bronze_tickets]).T


def handout_tickets(_holders, _tickets):
    """

    :return:
    """
    ticket_holders = {}

    for i, map_medal_holders in enumerate(_holders):
        for j, current_medal_type_medal_holders in enumerate(map_medal_holders):
            for medal_holder in current_medal_type_medal_holders:
                if medal_holder not in ticket_holders.keys():
                    ticket_holders[medal_holder] = _tickets[i][j]
                else:
                    ticket_holders[medal_holder] += _tickets[i][j]

    return ticket_holders


def retrieve_id_to_display_name_dict(participant_id_list):
    id_to_display_name_dict = {}
    # First retrieve "cached" account Ids and only retrieve new ones.
    try:
        # Try to open the file
        with open("participant_id_to_display_name_dict.json", 'r') as json_file:
            cached_conversion_dict = json.load(json_file)
    except FileNotFoundError:
        cached_conversion_dict = {}
        with open("participant_id_to_display_name_dict.json", 'w') as json_file:
            json.dump(cached_conversion_dict, json_file)

    collected_acc_infos = {}

    request_strings = []
    _i = 0
    request_string = ""
    for accId in participant_id_list:
        # If we already know this person, don't extend the request.
        if accId in cached_conversion_dict:
            continue

        request_string += f"accountId[]={accId}&"
        _i += 1

        if _i > 48:
            request_string = request_string[:-1]
            request_strings.append(request_string)
            request_string = ""
            _i = 0

    # Append the final result
    if request_string not in request_strings:
        request_string = request_string[:-1]
        request_strings.append(request_string)

    if request_strings[0] == "":
        print("All participant_ids are already in cached!")
    else:
        for request_string in request_strings:
            accountId_get_url = f"https://api.trackmania.com/api/display-names?{request_string}"
            print(f"Getting {accountId_get_url}")
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {access_token}"
            }

            response = requests.get(accountId_get_url, headers=headers)
            time.sleep(1)

            accInfos = response.json()
            collected_acc_infos.update(accInfos)

        cached_conversion_dict.update(collected_acc_infos)
        # Dump the newest cached version of all the accounts
        with open("participant_id_to_display_name_dict.json", "w") as json_file:
            json.dump(cached_conversion_dict, json_file)

    return cached_conversion_dict


# Retrieve the campaign data
campaign_data = retrieve_campaign_data("35145/50013")

# Then, retrieve the list of maps and their associated time requirements for gold/AT
map_list = extract_map_data(campaign_data["playlist"])

# # Next, we extract the records for each map
# records = collect_records(map_list)

with open(f"records.json", "r") as file:
    records = json.load(file)

counters, holders = collect_medal_occurences_per_map(map_list, records)

tickets = determine_tickets_per_map(counters)

print(tickets)

ticket_holders = handout_tickets(_holders=holders, _tickets=tickets)

id_to_name_dict = retrieve_id_to_display_name_dict(ticket_holders.keys())

# Replace IDs with names
ticket_holders = {id_to_name_dict[key]: value for key, value in ticket_holders.items()}

# print(ticket_holders)

# Print items sorted by value
sorted_items = sorted(ticket_holders.items(), key=lambda x: x[1], reverse=True)

for name, value in sorted_items:
    print(f"{name}: {value}")

print(len(sorted_items))
