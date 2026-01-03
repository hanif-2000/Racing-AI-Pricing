# racing/views.py

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import asyncio
import json

from .scraper import TABScraper, ElitebetScraper, LadbrokesScraper, TABtouchScraper


def calculate_ai_prices(participants, margin=1.30):
    if not participants:
        return participants
    
    total_prob = 0
    for p in participants:
        odds = p.get('odds', 0)
        if odds > 0:
            total_prob += 1 / odds
    
    for p in participants:
        odds = p.get('odds', 0)
        
        if odds > 0 and total_prob > 0:
            implied_prob = (1 / odds) / total_prob * 100
            fair_prob = implied_prob / margin
            ai_price = 100 / fair_prob if fair_prob > 0 else 0
            edge = ((odds - ai_price) / ai_price * 100) if ai_price > 0 else 0
            
            p['tab_odds'] = odds
            p['implied_prob'] = round(implied_prob, 1)
            p['fair_prob'] = round(fair_prob, 1)
            p['ai_price'] = round(ai_price, 2)
            p['edge'] = round(edge, 1)
            p['value'] = 'YES' if edge > 0 else 'NO'
        else:
            p['tab_odds'] = 0
            p['implied_prob'] = 0
            p['fair_prob'] = 0
            p['ai_price'] = 0
            p['edge'] = 0
            p['value'] = 'NO'
    
    return participants


@csrf_exempt
def get_ai_prices(request):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        all_meetings = []
        
        # Fetch TAB
        try:
            tab = TABScraper()
            tab_data = loop.run_until_complete(tab.get_all_jockey_data())
            all_meetings.extend(tab_data)
        except Exception as e:
            print(f"TAB error: {e}")
        
        # Fetch Elitebet
        try:
            elite = ElitebetScraper()
            elite_data = loop.run_until_complete(elite.get_all_jockey_data())
            all_meetings.extend(elite_data)
        except Exception as e:
            print(f"Elitebet error: {e}")
        
        # Fetch Ladbrokes
        try:
            ladbrokes = LadbrokesScraper()
            ladbrokes_data = loop.run_until_complete(ladbrokes.get_all_jockey_data())
            all_meetings.extend(ladbrokes_data)
        except Exception as e:
            print(f"Ladbrokes error: {e}")
        
        # Fetch TABtouch
        try:
            tabtouch = TABtouchScraper()
            tabtouch_data = loop.run_until_complete(tabtouch.get_all_jockey_data())
            all_meetings.extend(tabtouch_data)
        except Exception as e:
            print(f"TABtouch error: {e}")
        
        loop.close()
        
        # Process meetings
        jockey_meetings = []
        value_bets = 0
        
        for meeting in all_meetings:
            participants = []
            for j in meeting.get('jockeys', []):
                participants.append({
                    'name': j['name'],
                    'odds': j['odds']
                })
            
            meeting['participants'] = calculate_ai_prices(participants)
            meeting['total_participants'] = len(participants)
            value_bets += sum(1 for p in meeting['participants'] if p.get('value') == 'YES')
            jockey_meetings.append(meeting)
        
        return JsonResponse({
            'success': True,
            'jockey_challenges': jockey_meetings,
            'driver_challenges': [],
            'summary': {
                'total_jockey_meetings': len(jockey_meetings),
                'total_driver_meetings': 0,
                'total_value_bets': value_bets
            }
        })
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
            'jockey_challenges': [],
            'driver_challenges': [],
            'summary': {
                'total_jockey_meetings': 0,
                'total_driver_meetings': 0,
                'total_value_bets': 0
            }
        })


@csrf_exempt
def get_driver_challenges(request):
    return JsonResponse({'success': True, 'driver_challenges': []})


@csrf_exempt 
def refresh_data(request):
    return get_ai_prices(request)


# ============ BET TRACKER ============

BETS_STORAGE = []

@csrf_exempt
def add_bet(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            bet = {
                'id': len(BETS_STORAGE) + 1,
                'date': data.get('date'),
                'type': data.get('type', 'jockey'),
                'meeting': data.get('meeting'),
                'selection': data.get('selection'),
                'bookmaker': data.get('bookmaker'),
                'odds': float(data.get('odds', 0)),
                'stake': float(data.get('stake', 0)),
                'result': 'pending',
                'pnl': 0
            }
            BETS_STORAGE.append(bet)
            return JsonResponse({'success': True, 'bet': bet})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'POST required'})


@csrf_exempt
def update_bet_result(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            bet_id = data.get('bet_id')
            result = data.get('result')
            
            for bet in BETS_STORAGE:
                if bet['id'] == bet_id:
                    bet['result'] = result
                    if result == 'win':
                        bet['pnl'] = bet['stake'] * (bet['odds'] - 1)
                    elif result == 'loss':
                        bet['pnl'] = -bet['stake']
                    else:
                        bet['pnl'] = 0
                    return JsonResponse({'success': True, 'bet': bet})
            
            return JsonResponse({'success': False, 'error': 'Bet not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'POST required'})


def bet_summary(request):
    total_pnl = sum(b['pnl'] for b in BETS_STORAGE)
    wins = sum(1 for b in BETS_STORAGE if b['result'] == 'win')
    losses = sum(1 for b in BETS_STORAGE if b['result'] == 'loss')
    pending = sum(1 for b in BETS_STORAGE if b['result'] == 'pending')
    
    return JsonResponse({
        'success': True,
        'bets': BETS_STORAGE,
        'summary': {
            'total_bets': len(BETS_STORAGE),
            'wins': wins,
            'losses': losses,
            'pending': pending,
            'total_pnl': round(total_pnl, 2)
        }
    })