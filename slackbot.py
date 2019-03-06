from flask import Flask, request, abort, jsonify
from pymongo import MongoClient
from bson.objectid import ObjectId
import requests


app = Flask(__name__)
db = MongoClient().slackbot


slack_clients = {}


def slack(company_id, team_id):
    if slack_clients.get(company_id) and slack_clients[company_id].get(team_id):
        return slack_clients[company_id][team_id]
    else:
        token = db.access_tokens.find_one({'company_id': company_id, 'team_id': team_id}).get('access_token')
        if token:
            _client = SlackClient(token)
            slack_clients.update({ company_id: {team_id: _client} })
            return _client


@app.route('/slack', methods=['POST'])
def index():
    print('#'*30, request.json, '#'*30, sep='\n')
    return ''


@app.route('/slack/auth/<company_id>', methods=['GET'])
def auth_handler(company_id):
    code = request.args.get('code')
    if code and company_id:

        company = db.companies.find_one({'_id': ObjectId(company_id)})
        if not company:
            return abort(404)

        slack = SlackClient('')
        response = slack.api_call(
            'oauth.access', 
            code=code,
            client_id=company.get('client_id'),
            client_secret=company.get('client_secret')
        )
        if response.get('ok'):
            db.access_tokens.update_one(
                {'team_id': response['team_id']}, 
                {'$set': {'access_token': response['bot']['bot_access_token']}},
                upsert=True
            )
            return 'OK'
    return 'Error'


@app.route('/slack/events/<company_id>', methods=['POST'])
def events_handler(company_id):
    if not request.content_type == 'application/json' or not company_id:
        return abort(406)


    company = db.companies.find_one({'_id': ObjectId(company_id)})
    if not company:
        return abort(404)

    data = request.json

    if data.get('type') == 'url_verification':
        db.companies.update_one(
            {'_id': company.get('_id')},
            {'$set': {'verification_token': data.get('token')}}
        )
        return data.get('challenge')

    if data.get('token') == company.get('verification_token') and data['event']['channel_type'] == 'im':

        workspace = slack(company_id, data['team_id']).api_call('team.info')['team']
        user = slack(company_id, data['team_id']).api_call('users.info', user=data['event']['user'])['user']

        _data = {
            'contact': {
                'workspace': {
                    'id': data['team_id'],
                    'domain': workspace['domain'],
                    'channel': data['event']['channel']
                }, 
                'user': {
                    'id': data['event']['user'],
                    'name': user['name'],
                    'email': user['profile']['email'],
                    'avatar': {
                        'image_original': user['profile'].get(['image_original']),
                        'image_24': user['profile'].get(['image_24']),
                        'image_32': user['profile'].get(['image_32']),
                        'image_48': user['profile'].get(['image_48']),
                        'image_72': user['profile'].get(['image_72']),
                        'image_192': user['profile'].get(['image_192']),
                        'image_512': user['profile'].get(['image_512']),
                    }
                }
            },
            'message': {
                'text': data['event']['text'],
                'timestamp': data['event']['event_ts'],
                'files': data['event'].get('files')
            }
        }
        requests.post(company.get('webhook_url'), json=_data)

    return ''


@app.route('/slack/generate_webhook', methods=['GET'])
def generate_webhook():
    client_id = request.args.get('client_id')
    client_secret = request.args.get('client_secret')
    webhook_url = request.args.get('webhook_url')
    company_id = request.args.get('company_id')

    if client_id and client_secret and webhook_url and company_id:
        company_id = db.companies.insert_one({
            'client_id': client_id,
            'client_secret': client_secret,
            'webhook_url': webhook_url,
            'usedesk_id': company_id
        }).inserted_id
        return jsonify(ok=True, data={
            'auth_webhook': '/slack/auth/{}'.format(company_id), 
            'events_webhook': '/slack/events/{}'.format(company_id)
        })
    
    return jsonify(ok=False, data={'error': 'Missing argument'})


@app.route('/slack/send', methods=['POST'])
def send():
    if not request.content_type == 'application/json':
        return jsonify(ok=False, data={'error': 'Invalid content-type'})
    
    data = request.json

    usedesk_company_id = data.get('company_id')
    workspace_id = data.get('workspace_id')
    channel_id = data.get('channel_id')
    text = data.get('text')

    company = db.companies.find_one({'usedesk_id': usedesk_company_id})
    
    if company and workspace_id and channel_id and text:
        response = slack(str(company.get('_id')), workspace_id).api_call('chat.postMessage', channel=channel_id, text=text)
        return jsonify(ok=True, data={})
    
    return jsonify(ok=False, data={'error': 'Missing argument or company not found'})


if __name__ == "__main__":
    app.run(debug=True, port=5050)

