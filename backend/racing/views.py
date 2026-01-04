# racing/views.py - COMPLETE VERSION

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import asyncio
import json
import threading

from .scraper import fetch_all_data, get_cached_data, has_cached_data, CACHE


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


def process_meetings(jockey_meetings, driver_meetings):
    processed_jockey = []
    jockey_value_bets = 0
    
    for meeting in jockey_meetings:
        participants = []
        for j in meeting.get('jockeys', []):
            participants.append({'name': j['name'], 'odds': j['odds']})
        
        meeting['participants'] = calculate_ai_prices(participants)
        meeting['total_participants'] = len(participants)
        jockey_value_bets += sum(1 for p in meeting['participants'] if p.get('value') == 'YES')
        processed_jockey.append(meeting)
    
    processed_driver = []
    driver_value_bets = 0
    
    for meeting in driver_meetings:
        participants = []
        for d in meeting.get('drivers', meeting.get('jockeys', [])):
            participants.append({'name': d['name'], 'odds': d['odds']})
        
        meeting['participants'] = calculate_ai_prices(participants)
        meeting['total_participants'] = len(participants)
        driver_value_bets += sum(1 for p in meeting['participants'] if p.get('value') == 'YES')
        processed_driver.append(meeting)
    
    return processed_jockey, processed_driver, jockey_value_bets, driver_value_bets


def run_scraper_background():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(fetch_all_data())
    loop.close()


@csrf_exempt
def get_ai_prices(request):
    try:
        # Get country filter from query params (?country=AU or ?country=NZ or ?country=ALL)
        country_filter = request.GET.get('country', 'ALL').upper()
        
        def filter_by_country(meetings):
            if country_filter == 'ALL':
                return meetings
            return [m for m in meetings if m.get('country', 'AU') == country_filter]
        
        if has_cached_data():
            cached = get_cached_data()
            
            jockey_meetings = filter_by_country(cached.get('jockey_challenges', []))
            driver_meetings = filter_by_country(cached.get('driver_challenges', []))
            
            processed_jockey, processed_driver, jockey_value_bets, driver_value_bets = process_meetings(
                jockey_meetings, driver_meetings
            )
            
            if not CACHE.get('is_scraping'):
                thread = threading.Thread(target=run_scraper_background)
                thread.daemon = True
                thread.start()
            
            # Count by country
            all_jockey = cached.get('jockey_challenges', [])
            all_driver = cached.get('driver_challenges', [])
            au_count = len([m for m in all_jockey + all_driver if m.get('country', 'AU') == 'AU'])
            nz_count = len([m for m in all_jockey + all_driver if m.get('country', 'AU') == 'NZ'])
            
            return JsonResponse({
                'success': True,
                'jockey_challenges': processed_jockey,
                'driver_challenges': processed_driver,
                'summary': {
                    'total_jockey_meetings': len(processed_jockey),
                    'total_driver_meetings': len(processed_driver),
                    'jockey_value_bets': jockey_value_bets,
                    'driver_value_bets': driver_value_bets,
                    'total_value_bets': jockey_value_bets + driver_value_bets,
                    'au_meetings': au_count,
                    'nz_meetings': nz_count
                },
                'country_filter': country_filter,
                'last_updated': cached.get('last_updated'),
                'from_cache': True
            })
        
        print("📥 No cache found, fetching fresh data...")
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(fetch_all_data())
        loop.close()
        
        jockey_meetings = filter_by_country(result.get('jockey_challenges', []))
        driver_meetings = filter_by_country(result.get('driver_challenges', []))
        
        processed_jockey, processed_driver, jockey_value_bets, driver_value_bets = process_meetings(
            jockey_meetings, driver_meetings
        )
        
        # Count by country
        all_jockey = result.get('jockey_challenges', [])
        all_driver = result.get('driver_challenges', [])
        au_count = len([m for m in all_jockey + all_driver if m.get('country', 'AU') == 'AU'])
        nz_count = len([m for m in all_jockey + all_driver if m.get('country', 'AU') == 'NZ'])
        
        return JsonResponse({
            'success': True,
            'jockey_challenges': processed_jockey,
            'driver_challenges': processed_driver,
            'summary': {
                'total_jockey_meetings': len(processed_jockey),
                'total_driver_meetings': len(processed_driver),
                'jockey_value_bets': jockey_value_bets,
                'driver_value_bets': driver_value_bets,
                'total_value_bets': jockey_value_bets + driver_value_bets,
                'au_meetings': au_count,
                'nz_meetings': nz_count
            },
            'country_filter': country_filter,
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
            'summary': {'total_value_bets': 0}
        })


@csrf_exempt
def get_jockey_challenges(request):
    try:
        if has_cached_data():
            cached = get_cached_data()
            jockey_meetings = cached.get('jockey_challenges', [])
            processed, _, value_bets, _ = process_meetings(jockey_meetings, [])
            
            return JsonResponse({
                'success': True,
                'jockey_challenges': processed,
                'summary': {'total_meetings': len(processed), 'total_value_bets': value_bets}
            })
        
        return get_ai_prices(request)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e), 'jockey_challenges': []})


@csrf_exempt
def get_driver_challenges(request):
    try:
        if has_cached_data():
            cached = get_cached_data()
            driver_meetings = cached.get('driver_challenges', [])
            _, processed, _, value_bets = process_meetings([], driver_meetings)
            
            return JsonResponse({
                'success': True,
                'driver_challenges': processed,
                'summary': {'total_meetings': len(processed), 'total_value_bets': value_bets}
            })
        
        return get_ai_prices(request)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e), 'driver_challenges': []})


@csrf_exempt
def get_comparison(request):
    try:
        if has_cached_data():
            cached = get_cached_data()
            return JsonResponse({
                'success': True,
                'jockey_challenges': cached.get('jockey_challenges', []),
                'driver_challenges': cached.get('driver_challenges', []),
                'bookmakers': ['sportsbet', 'tabtouch', 'tab', 'ladbrokes', 'elitebet']
            })
        return get_ai_prices(request)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt 
def refresh_data(request):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(fetch_all_data())
        loop.close()
        return get_ai_prices(request)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


# BET TRACKER
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



    # =====================================================
# LIVE TRACKER
# =====================================================

from .live_tracker import LiveMeetingTracker

LIVE_TRACKERS = {}  # Store active trackers


@csrf_exempt
def get_all_live_trackers(request):
    """Get all active live trackers"""
    trackers = {}
    for meeting, tracker in LIVE_TRACKERS.items():
        trackers[meeting] = tracker.to_dict()
    
    return JsonResponse({'success': True, 'trackers': trackers, 'count': len(trackers)})


@csrf_exempt
def get_live_tracker(request, meeting_name):
    """Get live tracker data for a meeting"""
    meeting = meeting_name.upper()
    
    if meeting not in LIVE_TRACKERS:
        return JsonResponse({'success': False, 'error': 'Meeting not found'}, status=404)
    
    tracker = LIVE_TRACKERS[meeting]
    return JsonResponse({'success': True, **tracker.to_dict()})


@csrf_exempt
def init_live_tracker(request):
    """Initialize a live tracker from current scraped data"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        meeting_name = data.get('meeting', '').upper()
        challenge_type = data.get('type', 'jockey')
        total_races = data.get('total_races', 8)
        
        # Get participants from cached scrape data
        participants = []
        source_key = 'jockey_challenges' if challenge_type == 'jockey' else 'driver_challenges'
        
        for item in CACHE.get(source_key, []):
            if item['meeting'] == meeting_name:
                key = 'jockeys' if challenge_type == 'jockey' else 'drivers'
                participants = item.get(key, [])
                break
        
        if not participants:
            return JsonResponse({'success': False, 'error': f'No data found for {meeting_name}'}, status=404)
        
        # Create tracker
        tracker = LiveMeetingTracker(meeting_name, challenge_type)
        tracker.initialize_participants(participants, total_races)
        
        # Add bookmaker odds from all sources
        for item in CACHE.get(source_key, []):
            if item['meeting'] == meeting_name:
                source = item.get('source', 'unknown')
                key = 'jockeys' if challenge_type == 'jockey' else 'drivers'
                tracker.add_bookmaker_odds(source, item.get(key, []))
        
        LIVE_TRACKERS[meeting_name] = tracker
        
        return JsonResponse({'success': True, **tracker.to_dict()})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
def update_race_result(request):
    """Update race result for a meeting"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        meeting_name = data.get('meeting', '').upper()
        race_num = data.get('race_num', 0)
        results = data.get('results', [])
        
        if meeting_name not in LIVE_TRACKERS:
            return JsonResponse({'success': False, 'error': 'Meeting not found'}, status=404)
        
        tracker = LIVE_TRACKERS[meeting_name]
        tracker.update_race_result(race_num, results)
        
        # Re-scrape bookmaker odds after each race
        # (odds change after results)
        
        return JsonResponse({'success': True, **tracker.to_dict()})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)})


@csrf_exempt
def delete_live_tracker(request, meeting_name):
    """Delete a live tracker"""
    meeting = meeting_name.upper()
    
    if meeting in LIVE_TRACKERS:
        del LIVE_TRACKERS[meeting]
        return JsonResponse({'success': True, 'message': f'{meeting} tracker deleted'})
    
    return JsonResponse({'success': False, 'error': 'Meeting not found'}, status=404)