"""
🏇 RACING VIEWS - PRODUCTION VERSION
- No duplicate functions
- Proper error handling
- Input validation
- Clean API responses
"""

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.core.cache import cache
import asyncio
import json
import threading
from datetime import date, timedelta

from .scraper import fetch_all_data, get_cached_data, has_cached_data, CACHE, is_cache_stale, run_scraper_background
from .models import Meeting, Participant, MeetingOdds


# =====================================================
# AI PRICING CALCULATION
# =====================================================

def calculate_ai_prices(participants, margin=1.30):
    """Calculate AI prices with configurable margin"""
    if not participants:
        return participants
    
    total_prob = sum(1 / p.get('odds', 999) for p in participants if p.get('odds', 0) > 0)
    
    for p in participants:
        odds = p.get('odds', 0)
        if odds > 0 and total_prob > 0:
            implied_prob = (1 / odds) / total_prob * 100
            fair_prob = implied_prob / margin
            ai_price = 100 / fair_prob if fair_prob > 0 else 0
            edge = ((odds - ai_price) / ai_price * 100) if ai_price > 0 else 0
            
            p.update({
                'tab_odds': odds,
                'implied_prob': round(implied_prob, 1),
                'fair_prob': round(fair_prob, 1),
                'ai_price': round(ai_price, 2),
                'edge': round(edge, 1),
                'value': 'YES' if edge > 0 else 'NO'
            })
        else:
            p.update({
                'tab_odds': 0, 'implied_prob': 0, 'fair_prob': 0,
                'ai_price': 0, 'edge': 0, 'value': 'NO'
            })
    
    return participants


def process_meetings(jockey_meetings, driver_meetings, margin=1.30):
    """Process meetings and calculate AI prices"""
    jockey_value = driver_value = 0
    
    for m in jockey_meetings:
        participants = [{'name': j['name'], 'odds': j['odds']} for j in m.get('jockeys', [])]
        m['participants'] = calculate_ai_prices(participants, margin)
        m['total_participants'] = len(participants)
        jockey_value += sum(1 for p in m['participants'] if p.get('value') == 'YES')
    
    for m in driver_meetings:
        participants = [{'name': d['name'], 'odds': d['odds']} for d in m.get('drivers', m.get('jockeys', []))]
        m['participants'] = calculate_ai_prices(participants, margin)
        m['total_participants'] = len(participants)
        driver_value += sum(1 for p in m['participants'] if p.get('value') == 'YES')
    
    return jockey_meetings, driver_meetings, jockey_value, driver_value


# =====================================================
# MAIN API ENDPOINTS
# =====================================================

@csrf_exempt
def get_ai_prices(request):
    """Main API - Get all AI prices with bookmaker comparison"""
    try:
        # Get parameters
        country = request.GET.get('country', 'ALL').upper()
        margin = float(request.GET.get('margin', 1.30))
        
        def filter_country(meetings):
            if country == 'ALL':
                return meetings
            return [m for m in meetings if m.get('country', 'AU') == country]
        
        # Return cache if available
        if has_cached_data():
            cached = get_cached_data()
            jockey = filter_country(cached.get('jockey_challenges', []))
            driver = filter_country(cached.get('driver_challenges', []))
            
            jockey, driver, jv, dv = process_meetings(jockey, driver, margin)
            
            # Refresh in background if stale
            if is_cache_stale() and not CACHE.is_scraping:
                run_scraper_background()
            
            all_j = cached.get('jockey_challenges', [])
            all_d = cached.get('driver_challenges', [])
            au = len([m for m in all_j + all_d if m.get('country') == 'AU'])
            nz = len([m for m in all_j + all_d if m.get('country') == 'NZ'])
            
            return JsonResponse({
                'success': True,
                'jockey_challenges': jockey,
                'driver_challenges': driver,
                'summary': {
                    'total_jockey_meetings': len(jockey),
                    'total_driver_meetings': len(driver),
                    'jockey_value_bets': jv,
                    'driver_value_bets': dv,
                    'total_value_bets': jv + dv,
                    'au_meetings': au,
                    'nz_meetings': nz
                },
                'country_filter': country,
                'margin': margin,
                'last_updated': cached.get('last_updated'),
                'from_cache': True
            })
        
        # No cache - fetch fresh
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(fetch_all_data())
        loop.close()
        
        jockey = filter_country(result.get('jockey_challenges', []))
        driver = filter_country(result.get('driver_challenges', []))
        jockey, driver, jv, dv = process_meetings(jockey, driver, margin)
        
        all_j = result.get('jockey_challenges', [])
        all_d = result.get('driver_challenges', [])
        au = len([m for m in all_j + all_d if m.get('country') == 'AU'])
        nz = len([m for m in all_j + all_d if m.get('country') == 'NZ'])
        
        return JsonResponse({
            'success': True,
            'jockey_challenges': jockey,
            'driver_challenges': driver,
            'summary': {
                'total_jockey_meetings': len(jockey),
                'total_driver_meetings': len(driver),
                'jockey_value_bets': jv,
                'driver_value_bets': dv,
                'total_value_bets': jv + dv,
                'au_meetings': au,
                'nz_meetings': nz
            },
            'country_filter': country,
            'margin': margin,
            'last_updated': result.get('last_updated'),
            'from_cache': False
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({
            'success': False, 'error': str(e),
            'jockey_challenges': [], 'driver_challenges': [],
            'summary': {'total_value_bets': 0}
        }, status=500)


@csrf_exempt
def refresh_data(request):
    """Force refresh data"""
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(fetch_all_data())
        loop.close()
        return get_ai_prices(request)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def get_jockey_challenges(request):
    """Get only jockey challenges"""
    if has_cached_data():
        cached = get_cached_data()
        jockey, _, jv, _ = process_meetings(cached.get('jockey_challenges', []), [])
        return JsonResponse({
            'success': True,
            'jockey_challenges': jockey,
            'summary': {'total_meetings': len(jockey), 'total_value_bets': jv}
        })
    return get_ai_prices(request)


@csrf_exempt
def get_driver_challenges(request):
    """Get only driver challenges"""
    if has_cached_data():
        cached = get_cached_data()
        _, driver, _, dv = process_meetings([], cached.get('driver_challenges', []))
        return JsonResponse({
            'success': True,
            'driver_challenges': driver,
            'summary': {'total_meetings': len(driver), 'total_value_bets': dv}
        })
    return get_ai_prices(request)


@csrf_exempt
def get_comparison(request):
    """Get comparison data for all bookmakers"""
    if has_cached_data():
        cached = get_cached_data()
        return JsonResponse({
            'success': True,
            'jockey_challenges': cached.get('jockey_challenges', []),
            'driver_challenges': cached.get('driver_challenges', []),
            'bookmakers': ['tab', 'sportsbet', 'tabtouch', 'ladbrokes', 'elitebet', 'pointsbet']
        })
    return get_ai_prices(request)


# =====================================================
# BET TRACKER (Database-backed)
# =====================================================

from .models import Bet as BetModel

@csrf_exempt
def add_bet(request):
    """Add a new bet"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        
        # Validation
        required = ['selection', 'odds', 'stake']
        for field in required:
            if field not in data:
                return JsonResponse({'success': False, 'error': f'Missing {field}'}, status=400)
        
        bet = BetModel.objects.create(
            meeting_name=data.get('meeting', ''),
            participant=data.get('selection', ''),
            bookmaker=data.get('bookmaker', 'TAB'),
            odds=float(data.get('odds', 0)),
            stake=float(data.get('stake', 0)),
            result='pending'
        )
        
        return JsonResponse({
            'success': True,
            'bet': {
                'id': bet.id,
                'meeting': bet.meeting_name,
                'selection': bet.participant,
                'bookmaker': bet.bookmaker,
                'odds': bet.odds,
                'stake': bet.stake,
                'result': bet.result
            }
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def update_bet_result(request):
    """Update bet result"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        bet_id = data.get('bet_id')
        result = data.get('result')
        
        if result not in ['pending', 'win', 'loss']:
            return JsonResponse({'success': False, 'error': 'Invalid result'}, status=400)
        
        bet = BetModel.objects.get(id=bet_id)
        bet.result = result
        
        if result == 'win':
            bet.profit_loss = bet.stake * (bet.odds - 1)
        elif result == 'loss':
            bet.profit_loss = -bet.stake
        else:
            bet.profit_loss = 0
        
        bet.save()
        
        return JsonResponse({
            'success': True,
            'bet': {
                'id': bet.id,
                'result': bet.result,
                'profit_loss': bet.profit_loss
            }
        })
    except BetModel.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Bet not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def delete_bet(request):
    """Delete a bet"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        bet_id = data.get('bet_id')
        
        bet = BetModel.objects.get(id=bet_id)
        bet.delete()
        
        return JsonResponse({'success': True, 'message': 'Bet deleted'})
    except BetModel.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Bet not found'}, status=404)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def get_bets(request):
    """Get all bets"""
    bets = BetModel.objects.all().order_by('-created_at')
    return JsonResponse({
        'success': True,
        'bets': [{
            'id': b.id,
            'date': b.created_at.strftime('%Y-%m-%d'),
            'meeting': b.meeting_name,
            'selection': b.participant,
            'bookmaker': b.bookmaker,
            'odds': b.odds,
            'stake': b.stake,
            'result': b.result,
            'pnl': b.profit_loss or 0
        } for b in bets]
    })


def bet_summary(request):
    """Get bet summary stats"""
    bets = BetModel.objects.all()
    total_pnl = sum(b.profit_loss or 0 for b in bets)
    wins = bets.filter(result='win').count()
    losses = bets.filter(result='loss').count()
    pending = bets.filter(result='pending').count()
    
    return JsonResponse({
        'success': True,
        'summary': {
            'total_bets': bets.count(),
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

LIVE_TRACKERS = {}

@csrf_exempt
def get_all_live_trackers(request):
    """Get all active trackers"""
    return JsonResponse({
        'success': True,
        'trackers': {k: v.to_dict() for k, v in LIVE_TRACKERS.items()},
        'count': len(LIVE_TRACKERS)
    })


@csrf_exempt
def get_live_tracker(request, meeting_name):
    """Get tracker for specific meeting"""
    meeting = meeting_name.upper()
    if meeting not in LIVE_TRACKERS:
        return JsonResponse({'success': False, 'error': 'Meeting not found'}, status=404)
    return JsonResponse({'success': True, **LIVE_TRACKERS[meeting].to_dict()})


@csrf_exempt
def init_live_tracker(request):
    """Initialize a live tracker with adjustable margin"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        meeting = data.get('meeting', '').upper()
        ctype = data.get('type', 'jockey')
        total_races = data.get('total_races', 8)
        margin = float(data.get('margin', 1.30))  # Adjustable margin
        
        # Get participants from cache
        participants = []
        key = 'jockey_challenges' if ctype == 'jockey' else 'driver_challenges'
        
        for item in CACHE.jockey_challenges if ctype == 'jockey' else CACHE.driver_challenges:
            if item['meeting'] == meeting:
                pkey = 'jockeys' if ctype == 'jockey' else 'drivers'
                participants = item.get(pkey, [])
                break
        
        if not participants:
            return JsonResponse({'success': False, 'error': f'No data for {meeting}'}, status=404)
        
        tracker = LiveMeetingTracker(meeting, ctype, margin)  # Pass margin
        tracker.initialize_participants(participants, total_races)
        
        LIVE_TRACKERS[meeting] = tracker
        
        return JsonResponse({'success': True, **tracker.to_dict()})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def update_tracker_margin(request):
    """Update margin for a live tracker - AI prices will recalculate"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        meeting = data.get('meeting', '').upper()
        margin = float(data.get('margin', 1.30))
        
        # Validate margin (100% to 150%)
        if margin < 1.0 or margin > 1.5:
            return JsonResponse({'success': False, 'error': 'Margin must be between 1.0 (100%) and 1.5 (150%)'}, status=400)
        
        if meeting not in LIVE_TRACKERS:
            return JsonResponse({'success': False, 'error': 'Meeting not found'}, status=404)
        
        tracker = LIVE_TRACKERS[meeting]
        tracker.set_margin(margin)  # This recalculates AI prices
        
        return JsonResponse({
            'success': True,
            'message': f'Margin updated to {int(margin * 100)}%',
            **tracker.to_dict()
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def update_race_result(request):
    """Update race result for tracker"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        meeting = data.get('meeting', '').upper()
        race_num = data.get('race_num', 0)
        results = data.get('results', [])
        
        if meeting not in LIVE_TRACKERS:
            return JsonResponse({'success': False, 'error': 'Meeting not found'}, status=404)
        
        tracker = LIVE_TRACKERS[meeting]
        tracker.update_race_result(race_num, results)
        
        return JsonResponse({'success': True, **tracker.to_dict()})
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def delete_live_tracker(request, meeting_name):
    """Delete a tracker"""
    meeting = meeting_name.upper()
    if meeting in LIVE_TRACKERS:
        del LIVE_TRACKERS[meeting]
        return JsonResponse({'success': True, 'message': f'{meeting} deleted'})
    return JsonResponse({'success': False, 'error': 'Not found'}, status=404)


# =====================================================
# CALENDAR & HISTORY
# =====================================================

def calendar_view(request):
    """Get upcoming meetings for next 7 days"""
    today = date.today()
    end = today + timedelta(days=7)
    
    meetings = Meeting.objects.filter(date__gte=today, date__lte=end).order_by('date', 'name')
    
    calendar = {}
    for m in meetings:
        d = m.date.isoformat()
        if d not in calendar:
            calendar[d] = []
        calendar[d].append({
            'id': m.id, 'name': m.name, 'type': m.type,
            'country': m.country, 'status': m.status
        })
    
    return JsonResponse({'success': True, 'calendar': calendar, 'today': today.isoformat()})

def history_view(request):
    """Get meetings with correct status based on date"""
    days = int(request.GET.get('days', 30))
    today = date.today()
    start = today - timedelta(days=days)
    end = today + timedelta(days=7)  # Include upcoming meetings too
    
    meetings = Meeting.objects.filter(date__gte=start, date__lte=end).order_by('-date', 'name')
    
    history = []
    for m in meetings:
        # Calculate status based on date
        if m.date < today:
            status = 'completed'
        elif m.date == today:
            status = 'live'
        else:
            status = 'upcoming'
        
        participants = Participant.objects.filter(meeting=m).order_by('final_position')
        
        history.append({
            'id': m.id,
            'name': m.name,
            'date': m.date.isoformat(),
            'type': m.type,
            'country': m.country,
            'status': status,
            'participants': [
                {
                    'name': p.name,
                    'final_points': p.final_points,
                    'position': p.final_position
                } for p in participants
            ]
        })
    
    return JsonResponse({
        'success': True,
        'history': history,
        'days': days,
        'today': today.isoformat()
    })

def meeting_detail(request, meeting_id):
    """Get single meeting details"""
    try:
        m = Meeting.objects.get(id=meeting_id)
    except Meeting.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Not found'}, status=404)
    
    participants = Participant.objects.filter(meeting=m)
    odds = MeetingOdds.objects.filter(meeting=m).order_by('-timestamp')[:50]
    
    return JsonResponse({
        'success': True,
        'meeting': {
            'id': m.id, 'name': m.name, 'date': m.date.isoformat(),
            'type': m.type, 'country': m.country, 'status': m.status
        },
        'participants': [{'name': p.name, 'final_points': p.final_points, 'position': p.final_position} for p in participants],
        'odds_history': [{'participant': o.participant_name, 'bookmaker': o.bookmaker, 'odds': o.odds, 'timestamp': o.timestamp.isoformat()} for o in odds]
    })


@csrf_exempt
def save_meeting_result(request, meeting_id):
    """Save meeting results"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        m = Meeting.objects.get(id=meeting_id)
    except Meeting.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Not found'}, status=404)
    
    data = json.loads(request.body)
    results = data.get('results', [])
    
    for r in results:
        p, _ = Participant.objects.get_or_create(meeting=m, name=r['name'])
        p.final_points = r.get('points')
        p.final_position = r.get('position')
        p.save()
    
    m.status = 'completed'
    m.save()
    
    return JsonResponse({'success': True, 'message': f'Saved {m.name}'})


@csrf_exempt
def save_meeting_from_scrape(request):
    """Auto-save meeting from scrape"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    data = json.loads(request.body)
    today = date.today()
    
    m, created = Meeting.objects.get_or_create(
        name=data['name'].upper(),
        date=today,
        type=data.get('type', 'jockey'),
        defaults={'country': data.get('country', 'AU'), 'status': 'upcoming'}
    )
    
    participants = data.get('jockeys') or data.get('drivers') or []
    bookmaker = data.get('source', 'unknown')
    
    for p in participants:
        Participant.objects.get_or_create(meeting=m, name=p['name'])
        MeetingOdds.objects.create(meeting=m, participant_name=p['name'], bookmaker=bookmaker, odds=p['odds'])
    
    return JsonResponse({'success': True, 'meeting_id': m.id, 'created': created})


# =====================================================
# AUTO RESULTS
# =====================================================

@csrf_exempt
def fetch_race_results_api(request, meeting_name):
    """Fetch race results from Ladbrokes"""
    from .results_scraper import fetch_race_results
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(fetch_race_results(meeting_name))
        loop.close()
        
        return JsonResponse({
            'success': True,
            'meeting': meeting_name.upper(),
            'races': results.get('races', []),
            'last_updated': results.get('last_updated')
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def auto_update_tracker(request):
    """Auto-update tracker with latest results"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    from .results_scraper import fetch_race_results
    
    try:
        data = json.loads(request.body)
        meeting = data.get('meeting', '').upper()
        
        if meeting not in LIVE_TRACKERS:
            return JsonResponse({'success': False, 'error': 'Meeting not tracked'}, status=404)
        
        tracker = LIVE_TRACKERS[meeting]
        
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        results = loop.run_until_complete(fetch_race_results(meeting))
        loop.close()
        
        new_races = 0
        for race in results.get('races', []):
            race_num = race['race']
            if race_num <= tracker.races_completed:
                continue
            
            race_results = [{'position': r['position'], 'jockey': r['jockey']} for r in race['results']]
            if race_results:
                tracker.update_race_result(race_num, race_results)
                new_races += 1
        
        return JsonResponse({
            'success': True,
            'meeting': meeting,
            'new_races_added': new_races,
            **tracker.to_dict()
        })
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def auto_fetch_standings(request, meeting_name):
    """Auto-fetch standings from Ladbrokes"""
    from .auto_results import auto_update_meeting
    
    meeting = meeting_name.upper()
    
    # Get jockeys from cache
    jockeys = []
    for m in CACHE.jockey_challenges:
        if m['meeting'].upper() == meeting:
            jockeys = [j['name'] for j in m.get('jockeys', [])]
            break
    
    if not jockeys:
        for m in CACHE.driver_challenges:
            if m['meeting'].upper() == meeting:
                jockeys = [d['name'] for d in m.get('drivers', [])]
                break
    
    if not jockeys:
        # Try POST body
        if request.method == 'POST':
            data = json.loads(request.body)
            jockeys = data.get('jockeys', [])
    
    if not jockeys:
        return JsonResponse({'success': False, 'error': f'{meeting} not found'}, status=404)
    
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        result = loop.run_until_complete(auto_update_meeting(meeting_name, jockeys))
        loop.close()
        return JsonResponse(result)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)