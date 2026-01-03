# racing/views.py - WITH CACHING FOR INSTANT LOADING

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import asyncio
import json
import threading

from .scraper import fetch_all_data, get_cached_data, has_cached_data, CACHE


def calculate_ai_prices(participants, margin=1.30):
    """Calculate AI prices with edge detection"""
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


def process_meetings(jockey_meetings, driver_meetings):
    """Process raw meetings data with AI prices"""
    processed_jockey = []
    jockey_value_bets = 0
    
    for meeting in jockey_meetings:
        participants = []
        for j in meeting.get('jockeys', []):
            participants.append({
                'name': j['name'],
                'odds': j['odds']
            })
        
        meeting['participants'] = calculate_ai_prices(participants)
        meeting['total_participants'] = len(participants)
        jockey_value_bets += sum(1 for p in meeting['participants'] if p.get('value') == 'YES')
        processed_jockey.append(meeting)
    
    processed_driver = []
    driver_value_bets = 0
    
    for meeting in driver_meetings:
        participants = []
        for d in meeting.get('drivers', meeting.get('jockeys', [])):
            participants.append({
                'name': d['name'],
                'odds': d['odds']
            })
        
        meeting['participants'] = calculate_ai_prices(participants)
        meeting['total_participants'] = len(participants)
        driver_value_bets += sum(1 for p in meeting['participants'] if p.get('value') == 'YES')
        processed_driver.append(meeting)
    
    return processed_jockey, processed_driver, jockey_value_bets, driver_value_bets


def run_scraper_background():
    """Run scraper in background thread"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(fetch_all_data())
    loop.close()


@csrf_exempt
def get_ai_prices(request):
    """
    Main endpoint - Returns cached data INSTANTLY!
    Triggers background refresh if needed.
    """
    try:
        # If we have cached data, return it immediately
        if has_cached_data():
            cached = get_cached_data()
            
            jockey_meetings = cached.get('jockey_challenges', [])
            driver_meetings = cached.get('driver_challenges', [])
            
            processed_jockey, processed_driver, jockey_value_bets, driver_value_bets = process_meetings(
                jockey_meetings, driver_meetings
            )
            
            # Start background refresh (non-blocking)
            if not CACHE.get('is_scraping'):
                thread = threading.Thread(target=run_scraper_background)
                thread.daemon = True
                thread.start()
            
            return JsonResponse({
                'success': True,
                'jockey_challenges': processed_jockey,
                'driver_challenges': processed_driver,
                'summary': {
                    'total_jockey_meetings': len(processed_jockey),
                    'total_driver_meetings': len(processed_driver),
                    'jockey_value_bets': jockey_value_bets,
                    'driver_value_bets': driver_value_bets,
                    'total_value_bets': jockey_value_bets + driver_value_bets
                },
                'last_updated': cached.get('last_updated'),
                'from_cache': True
            })
        
        # No cache - need to fetch (first time only)
        print("📥 No cache found, fetching fresh data...")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(fetch_all_data())
        loop.close()
        
        jockey_meetings = result.get('jockey_challenges', [])
        driver_meetings = result.get('driver_challenges', [])
        
        processed_jockey, processed_driver, jockey_value_bets, driver_value_bets = process_meetings(
            jockey_meetings, driver_meetings
        )
        
        return JsonResponse({
            'success': True,
            'jockey_challenges': processed_jockey,
            'driver_challenges': processed_driver,
            'summary': {
                'total_jockey_meetings': len(processed_jockey),
                'total_driver_meetings': len(processed_driver),
                'jockey_value_bets': jockey_value_bets,
                'driver_value_bets': driver_value_bets,
                'total_value_bets': jockey_value_bets + driver_value_bets
            },
            'last_updated': result.get('last_updated'),
            'from_cache': False
        })
        
    except Exception as e:
        import traceback
        print(f"❌ Error: {e}")
        print(traceback.format_exc())
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
def get_jockey_challenges(request):
    """Get jockey challenges only"""
    try:
        if has_cached_data():
            cached = get_cached_data()
            jockey_meetings = cached.get('jockey_challenges', [])
            
            processed, _, value_bets, _ = process_meetings(jockey_meetings, [])
            
            return JsonResponse({
                'success': True,
                'jockey_challenges': processed,
                'summary': {
                    'total_meetings': len(processed),
                    'total_value_bets': value_bets
                }
            })
        
        # Trigger fetch if no cache
        return get_ai_prices(request)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
            'jockey_challenges': []
        })


@csrf_exempt
def get_driver_challenges(request):
    """Get driver challenges only"""
    try:
        if has_cached_data():
            cached = get_cached_data()
            driver_meetings = cached.get('driver_challenges', [])
            
            _, processed, _, value_bets = process_meetings([], driver_meetings)
            
            return JsonResponse({
                'success': True,
                'driver_challenges': processed,
                'summary': {
                    'total_meetings': len(processed),
                    'total_value_bets': value_bets
                }
            })
        
        return get_ai_prices(request)
        
    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e),
            'driver_challenges': []
        })


@csrf_exempt 
def refresh_data(request):
    """Force refresh data"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(fetch_all_data())
        loop.close()
        
        return get_ai_prices(request)
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


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


@csrf_exempt
def delete_bet(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
            bet_id = data.get('bet_id')
            
            global BETS_STORAGE
            original_len = len(BETS_STORAGE)
            BETS_STORAGE = [b for b in BETS_STORAGE if b['id'] != bet_id]
            
            if len(BETS_STORAGE) < original_len:
                return JsonResponse({'success': True, 'message': 'Bet deleted'})
            return JsonResponse({'success': False, 'error': 'Bet not found'})
        except Exception as e:
            return JsonResponse({'success': False, 'error': str(e)})
    return JsonResponse({'success': False, 'error': 'POST required'})


def get_bets(request):
    return JsonResponse({'success': True, 'bets': BETS_STORAGE})


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
            'win_rate': round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0,
            'total_pnl': round(total_pnl, 2)
        }
    })