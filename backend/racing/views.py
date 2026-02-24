"""
RACING VIEWS - PRODUCTION VERSION (FIXED)
Database Persistence + Auto Results + All Endpoints
"""

import logging
logger = logging.getLogger(__name__)

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.utils import timezone
from django.db import transaction
import json
import copy
from datetime import date, timedelta

from .models import (
    Meeting, Participant, MeetingOdds, Bet as BetModel,
    GlobalState, ScrapedDataManager, OddsSnapshot,
    LiveTrackerState, AutoFetchConfig, PointsLedger
)


# =====================================================
# SCRAPED DATA CACHE (from GitHub Actions)
# =====================================================

SCRAPED_DATA = {
    'jockey_challenges': [],
    'driver_challenges': [],
    'last_updated': None
}


# =====================================================
# HELPER: Get data from DB or memory
# =====================================================

def get_scraped_data_from_db():
    """Get scraped data from database (persistent)"""
    return ScrapedDataManager.get_scraped_data()


def save_scraped_data_to_db(data):
    """Save scraped data to database"""
    ScrapedDataManager.save_scraped_data(
        data.get('jockey_challenges', []),
        data.get('driver_challenges', [])
    )


# =====================================================
# RECEIVE SCRAPED DATA FROM GITHUB ACTIONS
# =====================================================

@csrf_exempt
def receive_scrape(request):
    """Receive scraped data from GitHub Actions"""
    global SCRAPED_DATA
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        body = request.body.decode('utf-8')
        data = json.loads(body)
        
        SCRAPED_DATA['jockey_challenges'] = data.get('jockey_challenges', [])
        SCRAPED_DATA['driver_challenges'] = data.get('driver_challenges', [])
        SCRAPED_DATA['last_updated'] = data.get('last_updated')
        
        jockey_count = len(SCRAPED_DATA['jockey_challenges'])
        driver_count = len(SCRAPED_DATA['driver_challenges'])
        
        save_meetings_to_db(SCRAPED_DATA)
        save_scraped_data_to_db(SCRAPED_DATA)
        
        return JsonResponse({
            'success': True,
            'message': 'Data received',
            'jockey_meetings': jockey_count,
            'driver_meetings': driver_count,
            'last_updated': SCRAPED_DATA['last_updated']
        }, json_dumps_params={'ensure_ascii': False})
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def save_meetings_to_db(data):
    """Save meetings to database for calendar/history"""
    today = date.today()
    
    try:
        for m in data.get('jockey_challenges', []):
            meeting, _ = Meeting.objects.get_or_create(
                name=m['meeting'].upper(),
                date=today,
                type='jockey',
                defaults={'country': m.get('country', 'AU'), 'status': 'upcoming'}
            )
            source = m.get('source', 'unknown')
            for j in m.get('jockeys', []):
                Participant.objects.get_or_create(meeting=meeting, name=j['name'])
                if j.get('odds', 0) > 0:
                    MeetingOdds.objects.create(
                        meeting=meeting,
                        participant_name=j['name'],
                        bookmaker=source,
                        odds=j['odds']
                    )
        
        for m in data.get('driver_challenges', []):
            meeting, _ = Meeting.objects.get_or_create(
                name=m['meeting'].upper(),
                date=today,
                type='driver',
                defaults={'country': m.get('country', 'AU'), 'status': 'upcoming'}
            )
            source = m.get('source', 'unknown')
            for d in m.get('drivers', []):
                Participant.objects.get_or_create(meeting=meeting, name=d['name'])
                if d.get('odds', 0) > 0:
                    MeetingOdds.objects.create(
                        meeting=meeting,
                        participant_name=d['name'],
                        bookmaker=source,
                        odds=d['odds']
                    )
    except Exception as e:
        logger.error(f"Error saving to DB: {e}")


# =====================================================
# AI PRICING CALCULATION
# =====================================================

def merge_meetings(meetings, participant_key='jockeys'):
    """Merge duplicate meetings from different bookmakers into one with averaged odds"""
    merged = {}
    for m in meetings:
        name = m['meeting'].upper()
        source = m.get('source', 'unknown')
        if name not in merged:
            merged[name] = {
                'meeting': name,
                'type': m.get('type', 'jockey'),
                'country': m.get('country', 'AU'),
                'sources': [source],
                'participants_by_name': {},
            }
        else:
            if source not in merged[name]['sources']:
                merged[name]['sources'].append(source)

        for p in m.get(participant_key, []):
            pname = p['name']
            odds = p.get('odds', 0)
            if pname not in merged[name]['participants_by_name']:
                merged[name]['participants_by_name'][pname] = {
                    'name': pname,
                    'all_odds': {},
                }
            if odds > 0:
                merged[name]['participants_by_name'][pname]['all_odds'][source] = odds

    result = []
    for name, data in merged.items():
        participants = []
        for pname, pdata in data['participants_by_name'].items():
            all_odds = pdata['all_odds']
            if all_odds:
                avg_odds = round(sum(all_odds.values()) / len(all_odds), 2)
                best_odds = max(all_odds.values())
            else:
                avg_odds = 0
                best_odds = 0
            participants.append({
                'name': pname,
                'odds': avg_odds,
                'best_odds': best_odds,
                'all_odds': all_odds,
                'num_bookmakers': len(all_odds),
            })
        entry = {
            'meeting': data['meeting'],
            'type': data['type'],
            'country': data['country'],
            'sources': data['sources'],
            participant_key: participants,
        }
        result.append(entry)
    return result


def calculate_ai_prices(participants, margin=1.02):
    """Calculate AI prices using proportional overround removal.

    Standard bookmaker pricing model:
    1. Calculate total implied probability from averaged odds (includes overround)
    2. Normalize probabilities to 100% (removes ALL overround proportionally)
    3. AI price = true fair odds (what the price SHOULD be without margin)
    4. Edge = how much the best available bookmaker odds exceed fair price
    5. Value = YES when edge >= margin threshold

    Key: You need multiple bookmakers to find value. If best_odds at one
    bookmaker exceeds the fair price derived from the market consensus,
    that bookmaker is offering value on that selection.
    """
    if not participants:
        return participants

    margin_pct = (margin - 1.0) * 100 if margin >= 1.0 else margin

    valid = [p for p in participants if p.get('odds', 0) > 0]
    if not valid:
        return participants

    # Total implied probability from averaged odds (overround included)
    total_prob = sum(1 / p['odds'] for p in valid)
    overround_pct = round((total_prob - 1.0) * 100, 1)

    for p in participants:
        odds = p.get('odds', 0)
        best_odds = p.get('best_odds', odds)
        num_books = p.get('num_bookmakers', 1)

        if odds > 0 and total_prob > 0:
            raw_prob = 1 / odds

            # Fair probability: normalize to 100% (full overround removal)
            fair_prob = (raw_prob / total_prob) * 100
            fair_price = round(100 / fair_prob, 2) if fair_prob > 0 else 0

            # AI price = fair price (true odds, no bookmaker margin)
            ai_price = fair_price

            # Edge: best available odds vs fair AI price
            # Positive edge = bookmaker offers better than fair value
            edge = ((best_odds - ai_price) / ai_price * 100) if ai_price > 0 else 0

            p.update({
                'tab_odds': best_odds,
                'avg_odds': odds,
                'implied_prob': round(raw_prob * 100, 1),
                'fair_prob': round(fair_prob, 1),
                'ai_price': ai_price,
                'fair_price': fair_price,
                'edge': round(edge, 1),
                'value': 'YES' if edge >= margin_pct else 'NO',
                'num_bookmakers': num_books,
                'overround': overround_pct,
            })
        else:
            p.update({
                'tab_odds': 0, 'avg_odds': 0, 'implied_prob': 0, 'fair_prob': 0,
                'ai_price': 0, 'fair_price': 0, 'edge': 0, 'value': 'NO',
                'num_bookmakers': 0, 'overround': 0,
            })

    return participants


def process_meetings(jockey_meetings, driver_meetings, margin=1.02):
    """Process meetings: merge bookmakers, calculate AI prices"""
    jockey_value = driver_value = 0

    # Merge duplicate meetings from different bookmakers
    jockey_meetings = merge_meetings(jockey_meetings, 'jockeys')
    driver_meetings = merge_meetings(driver_meetings, 'drivers')

    for m in jockey_meetings:
        participants = m.get('jockeys', [])
        m['participants'] = calculate_ai_prices(participants, margin)
        m['total_participants'] = len(participants)
        jockey_value += sum(1 for p in m['participants'] if p.get('value') == 'YES')

    for m in driver_meetings:
        participants = m.get('drivers', m.get('jockeys', []))
        m['participants'] = calculate_ai_prices(participants, margin)
        m['total_participants'] = len(participants)
        driver_value += sum(1 for p in m['participants'] if p.get('value') == 'YES')

    return jockey_meetings, driver_meetings, jockey_value, driver_value


# =====================================================
# MAIN API ENDPOINTS
# =====================================================

@csrf_exempt
def get_ai_prices(request):
    """Main API - Get all AI prices"""
    global SCRAPED_DATA
    
    try:
        country = request.GET.get('country', 'ALL').upper()
        margin = float(request.GET.get('margin', 1.02))
        use_db = request.GET.get('persistent', 'false').lower() == 'true'
        
        # Use database if requested or if memory is empty
        if use_db or (not SCRAPED_DATA.get('jockey_challenges') and not SCRAPED_DATA.get('driver_challenges')):
            source_data = get_scraped_data_from_db()
            source = 'database'
        else:
            source_data = SCRAPED_DATA
            source = 'memory'
        
        def filter_country(meetings):
            if country == 'ALL':
                return meetings
            return [m for m in meetings if m.get('country', 'AU') == country]
        
        jockey = filter_country(source_data.get('jockey_challenges', []))
        driver = filter_country(source_data.get('driver_challenges', []))
        
        jockey, driver, jv, dv = process_meetings(copy.deepcopy(jockey), copy.deepcopy(driver), margin)
        
        all_j = source_data.get('jockey_challenges', [])
        all_d = source_data.get('driver_challenges', [])
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
            'last_updated': source_data.get('last_updated'),
            'source': source
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
def get_jockey_challenges(request):
    """Get only jockey challenges"""
    if not SCRAPED_DATA.get('jockey_challenges'):
        source_data = get_scraped_data_from_db()
    else:
        source_data = SCRAPED_DATA
    jockey = copy.deepcopy(source_data.get('jockey_challenges', []))
    margin = float(request.GET.get('margin', 1.02))
    jockey, _, jv, _ = process_meetings(jockey, [], margin)
    return JsonResponse({
        'success': True,
        'jockey_challenges': jockey,
        'summary': {'total_meetings': len(jockey), 'total_value_bets': jv}
    })


@csrf_exempt
def get_driver_challenges(request):
    """Get only driver challenges"""
    if not SCRAPED_DATA.get('driver_challenges'):
        source_data = get_scraped_data_from_db()
    else:
        source_data = SCRAPED_DATA
    driver = copy.deepcopy(source_data.get('driver_challenges', []))
    margin = float(request.GET.get('margin', 1.02))
    _, driver, _, dv = process_meetings([], driver, margin)
    return JsonResponse({
        'success': True,
        'driver_challenges': driver,
        'summary': {'total_meetings': len(driver), 'total_value_bets': dv}
    })


@csrf_exempt
def get_comparison(request):
    """Get comparison data for all bookmakers"""
    if not SCRAPED_DATA.get('jockey_challenges') and not SCRAPED_DATA.get('driver_challenges'):
        source_data = get_scraped_data_from_db()
    else:
        source_data = SCRAPED_DATA
    return JsonResponse({
        'success': True,
        'jockey_challenges': source_data.get('jockey_challenges', []),
        'driver_challenges': source_data.get('driver_challenges', []),
        'bookmakers': ['tabtouch', 'ladbrokes', 'elitebet', 'pointsbet']
    })


@csrf_exempt
def refresh_data(request):
    """Refresh data endpoint"""
    return JsonResponse({
        'success': True,
        'message': 'Data refreshes automatically every 5 minutes via GitHub Actions',
        'last_updated': SCRAPED_DATA.get('last_updated')
    })


# =====================================================
# BET TRACKER
# =====================================================

@csrf_exempt
def add_bet(request):
    """Add a new bet"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)

        meeting = data.get('meeting', '').strip()
        selection = data.get('selection', '').strip()
        bookmaker = data.get('bookmaker', 'TAB').strip()
        odds = float(data.get('odds', 0))
        stake = float(data.get('stake', 0))

        errors = []
        if not meeting:
            errors.append('meeting is required')
        if not selection:
            errors.append('selection is required')
        if odds <= 1.0:
            errors.append('odds must be greater than 1.0')
        if stake <= 0:
            errors.append('stake must be greater than 0')
        if stake > 100000:
            errors.append('stake cannot exceed 100000')

        if errors:
            return JsonResponse({'success': False, 'error': ', '.join(errors)}, status=400)

        bet = BetModel.objects.create(
            meeting_name=meeting,
            participant=selection,
            bookmaker=bookmaker,
            odds=odds,
            stake=stake,
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
    except (ValueError, TypeError) as e:
        return JsonResponse({'success': False, 'error': f'Invalid data: {e}'}, status=400)
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
            'bet': {'id': bet.id, 'result': bet.result, 'profit_loss': bet.profit_loss}
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
    
    return JsonResponse({
        'success': True,
        'summary': {
            'total_bets': bets.count(),
            'wins': wins,
            'losses': losses,
            'pending': bets.filter(result='pending').count(),
            'win_rate': round(wins / (wins + losses) * 100, 1) if (wins + losses) > 0 else 0,
            'total_pnl': round(total_pnl, 2)
        }
    })


# =====================================================
# LIVE TRACKER - DATABASE PERSISTENCE (FIXED!)
# =====================================================

def _build_leaderboard(participants, margin=1.30):
    """Helper to build leaderboard from participants dict"""
    leaderboard = []
    
    for name, data in participants.items():
        leaderboard.append({
            'name': name,
            'points': data.get('current_points', 0),
            'rides_remaining': data.get('rides_remaining', 0),
            'rides_total': data.get('rides_total', 0),
            'starting_odds': data.get('starting_odds', 0),
            'ai_price': data.get('ai_price', 0),
            'value': data.get('value', 'NO'),
            'positions': data.get('positions', []),
            'points_history': data.get('points_history', [])
        })
    
    leaderboard.sort(key=lambda x: (-x['points'], x['ai_price']))
    
    for i, item in enumerate(leaderboard):
        item['rank'] = i + 1
    
    return leaderboard


def _recalculate_ai_prices(participants, races_completed, margin=1.02):
    """Recalculate AI prices based on current standings.

    AI price = fair price (no margin multiplier).
    Margin is used as VALUE threshold only:
    margin 1.02 = 2% threshold, 1.10 = 10% threshold.
    """
    if not participants:
        return participants

    # Convert margin to percentage threshold
    margin_pct = (margin - 1.0) * 100 if margin >= 1.0 else margin

    standings = []
    for name, data in participants.items():
        current_points = data.get('current_points', 0)
        rides_remaining = data.get('rides_remaining', 0)
        starting_odds = data.get('starting_odds', 0)

        if races_completed > 0:
            avg_points = current_points / races_completed
            estimated_final = current_points + (avg_points * rides_remaining)
        else:
            estimated_final = 1 / starting_odds if starting_odds > 0 else 0

        standings.append({
            'name': name,
            'current_points': current_points,
            'estimated_final': estimated_final
        })

    standings.sort(key=lambda x: (-x['current_points'], -x['estimated_final']))

    total_estimated = sum(s['estimated_final'] for s in standings) or 1

    for s in standings:
        name = s['name']
        prob = (s['estimated_final'] / total_estimated) * 100

        if prob > 0:
            fair_price = 100 / prob
            ai_price = round(fair_price, 2)
        else:
            ai_price = 999

        starting_odds = participants[name].get('starting_odds', 0)
        edge = ((starting_odds - ai_price) / ai_price * 100) if ai_price > 0 and starting_odds > 0 else 0
        participants[name]['ai_price'] = ai_price
        participants[name]['value'] = 'YES' if edge >= margin_pct else 'NO'

    return participants


@csrf_exempt
def get_all_live_trackers(request):
    """Get all active trackers from DATABASE"""
    trackers = LiveTrackerState.objects.filter(is_active=True)
    
    result = {}
    for tracker in trackers:
        participants = tracker.get_participants()
        leaderboard = _build_leaderboard(participants, tracker.margin)
        
        result[tracker.meeting_name] = {
            'success': True,
            'meeting': tracker.meeting_name,
            'type': tracker.meeting_type,
            'margin': tracker.margin,
            'total_races': tracker.total_races,
            'races_completed': tracker.races_completed,
            'races_remaining': tracker.total_races - tracker.races_completed,
            'leaderboard': leaderboard,
            'race_results': tracker.get_race_results(),
            'updated_at': tracker.updated_at.isoformat()
        }
    
    return JsonResponse({
        'success': True,
        'trackers': result,
        'count': len(result)
    })


@csrf_exempt
def get_live_tracker(request, meeting_name):
    """Get tracker for specific meeting from DATABASE"""
    meeting = meeting_name.upper()
    
    try:
        tracker = LiveTrackerState.objects.get(meeting_name=meeting)
    except LiveTrackerState.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Meeting not found'}, status=404)
    
    participants = tracker.get_participants()
    leaderboard = _build_leaderboard(participants, tracker.margin)
    
    return JsonResponse({
        'success': True,
        'meeting': tracker.meeting_name,
        'type': tracker.meeting_type,
        'margin': tracker.margin,
        'total_races': tracker.total_races,
        'races_completed': tracker.races_completed,
        'races_remaining': tracker.total_races - tracker.races_completed,
        'leaderboard': leaderboard,
        'race_results': tracker.get_race_results(),
        'updated_at': tracker.updated_at.isoformat()
    })


@csrf_exempt
def init_live_tracker(request):
    """Initialize a live tracker - SAVES TO DATABASE"""
    global SCRAPED_DATA
    
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        meeting = data.get('meeting', '').upper()
        ctype = data.get('type', 'jockey')
        total_races = data.get('total_races', 8)
        margin = float(data.get('margin', 1.30))
        
        # Get participants from scraped data
        if not SCRAPED_DATA.get('jockey_challenges'):
            source_data = get_scraped_data_from_db()
        else:
            source_data = SCRAPED_DATA
        
        participants = []
        challenges = source_data.get('jockey_challenges' if ctype == 'jockey' else 'driver_challenges', [])
        
        for item in challenges:
            if item['meeting'].upper() == meeting:
                pkey = 'jockeys' if ctype == 'jockey' else 'drivers'
                participants = item.get(pkey, [])
                break
        
        if not participants:
            return JsonResponse({'success': False, 'error': f'No data for {meeting}'}, status=404)
        
        # Build participants dict
        participants_data = {}
        for p in participants:
            name = p.get('name', '')
            participants_data[name] = {
                'name': name,
                'starting_odds': p.get('odds', 0),
                'current_points': 0,
                'rides_total': total_races,
                'rides_remaining': total_races,
                'positions': [],
                'points_history': [],
                'ai_price': 0,
                'value': 'NO'
            }
        
        # Calculate initial AI prices
        participants_data = _recalculate_ai_prices(participants_data, 0, margin)
        
        # Save to DATABASE
        tracker, created = LiveTrackerState.objects.update_or_create(
            meeting_name=meeting,
            defaults={
                'meeting_type': ctype,
                'margin': margin,
                'total_races': total_races,
                'races_completed': 0,
                'is_active': True,
                'race_results_data': '[]'
            }
        )
        tracker.set_participants(participants_data)
        tracker.save()
        
        # Also create AutoFetchConfig for this meeting
        config, _ = AutoFetchConfig.objects.update_or_create(
            meeting_name=meeting,
            defaults={
                'meeting_type': ctype,
                'is_enabled': True,
                'total_races': total_races
            }
        )
        config.set_jockeys_list(list(participants_data.keys()))
        config.save()
        
        leaderboard = _build_leaderboard(participants_data, margin)
        
        return JsonResponse({
            'success': True,
            'meeting': meeting,
            'type': ctype,
            'margin': margin,
            'total_races': total_races,
            'races_completed': 0,
            'races_remaining': total_races,
            'leaderboard': leaderboard,
            'race_results': [],
            'storage': 'database'
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def update_race_result(request):
    """Update race result for tracker - SAVES TO DATABASE"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        meeting = data.get('meeting', '').upper()
        race_num = data.get('race_num', 0)
        results = data.get('results', [])
        actual_total_races = data.get('actual_total_races', None)

        if not meeting or not race_num:
            return JsonResponse({'success': False, 'error': 'meeting and race_num required'}, status=400)

        with transaction.atomic():
            try:
                tracker = LiveTrackerState.objects.select_for_update().get(meeting_name=meeting)
            except LiveTrackerState.DoesNotExist:
                return JsonResponse({'success': False, 'error': 'Meeting not found'}, status=404)

            # Update total_races if actual count provided and different
            if actual_total_races and actual_total_races != tracker.total_races:
                print(f"[Tracker] Updating {meeting} total_races: {tracker.total_races} -> {actual_total_races}")
                tracker.total_races = actual_total_races
                # Also update rides_remaining for all participants
                participants = tracker.get_participants()
                for name, pdata in participants.items():
                    races_done = len(pdata.get('positions', []))
                    pdata['rides_total'] = actual_total_races
                    pdata['rides_remaining'] = max(0, actual_total_races - races_done)
                tracker.set_participants(participants)

            if race_num <= tracker.races_completed:
                # Check if stored results differ (correction needed)
                stored_results = tracker.get_race_results()
                stored_race = None
                for sr in stored_results:
                    if sr.get('race') == race_num:
                        stored_race = sr
                        break

                needs_correction = False
                if stored_race:
                    old_names = {r.get('jockey', r.get('name', '')).lower() for r in stored_race.get('results', [])}
                    new_names = {r.get('jockey', r.get('name', '')).lower() for r in results}
                    if old_names != new_names:
                        needs_correction = True
                        print(f"[Tracker] CORRECTION for {meeting} R{race_num}: {old_names} -> {new_names}")

                if not needs_correction:
                    return JsonResponse({'success': True, 'message': 'Race already processed'})

                # Reset meeting to reprocess all races from scratch
                print(f"[Tracker] Resetting {meeting} for correction...")
                participants = tracker.get_participants()
                for name, pdata in participants.items():
                    pdata['current_points'] = 0
                    pdata['positions'] = []
                    pdata['points_history'] = []
                    pdata['rides_remaining'] = tracker.total_races
                tracker.set_participants(participants)
                tracker.races_completed = 0
                tracker.race_results_data = '[]'
                tracker.save()

                # Return requesting all results be re-sent
                return JsonResponse({
                    'success': True,
                    'message': 'Correction detected - meeting reset',
                    'reset': True
                })

            participants = tracker.get_participants()

            # Points system
            points_map = {1: 3, 2: 2, 3: 1}

            # Count positions for dead heat detection
            position_counts = {}
            for r in results:
                pos = r.get('position', 0)
                if pos in [1, 2, 3]:
                    position_counts[pos] = position_counts.get(pos, 0) + 1

            # Track who got points
            participants_in_race = set()

            for r in results:
                jockey = r.get('jockey', r.get('driver', r.get('name', '')))
                position = r.get('position', 0)

                # Find matching participant (case-insensitive)
                matched_name = None
                for pname in participants.keys():
                    if pname.lower() == jockey.lower() or jockey.lower() in pname.lower() or pname.lower() in jockey.lower():
                        matched_name = pname
                        break

                if matched_name and position in [1, 2, 3]:
                    participants_in_race.add(matched_name)

                    # Calculate points with dead heat
                    num_at_position = position_counts.get(position, 1)

                    if num_at_position > 1:
                        positions_consumed = list(range(position, min(position + num_at_position, 4)))
                        total_points = sum(points_map.get(p, 0) for p in positions_consumed)
                        points = round(total_points / num_at_position, 1)
                    else:
                        points = points_map.get(position, 0)

                    participants[matched_name]['current_points'] += points
                    participants[matched_name]['positions'].append(position)
                    participants[matched_name]['points_history'].append(points)
                    participants[matched_name]['rides_remaining'] -= 1

            # Mark non-placed participants
            for name, pdata in participants.items():
                if name not in participants_in_race and pdata['rides_remaining'] > 0:
                    pdata['rides_remaining'] -= 1
                    pdata['positions'].append(0)
                    pdata['points_history'].append(0)

            # Recalculate AI prices
            participants = _recalculate_ai_prices(participants, race_num, tracker.margin)

            # Save race result
            race_result = {
                'race': race_num,
                'results': results,
                'dead_heats': {pos: count for pos, count in position_counts.items() if count > 1},
                'timestamp': timezone.now().isoformat()
            }

            # Update tracker in DATABASE
            tracker.set_participants(participants)
            tracker.races_completed = race_num
            tracker.add_race_result(race_result)
            tracker.save()

            # Also save to PointsLedger for history
            today = date.today()
            for r in results:
                jockey = r.get('jockey', r.get('driver', r.get('name', '')))
                position = r.get('position', 0)

                if position in [1, 2, 3]:
                    num_at_position = position_counts.get(position, 1)
                    is_dead_heat = num_at_position > 1

                    if is_dead_heat:
                        positions_consumed = list(range(position, min(position + num_at_position, 4)))
                        total_points = sum(points_map.get(p, 0) for p in positions_consumed)
                        points = round(total_points / num_at_position, 1)
                    else:
                        points = points_map.get(position, 0)

                    PointsLedger.objects.update_or_create(
                        meeting_name=meeting,
                        meeting_date=today,
                        participant_name=jockey,
                        race_number=race_num,
                        defaults={
                            'participant_type': tracker.meeting_type,
                            'position': position,
                            'points_earned': points,
                            'is_dead_heat': is_dead_heat
                        }
                    )

        leaderboard = _build_leaderboard(participants, tracker.margin)

        return JsonResponse({
            'success': True,
            'meeting': meeting,
            'type': tracker.meeting_type,
            'margin': tracker.margin,
            'total_races': tracker.total_races,
            'races_completed': tracker.races_completed,
            'races_remaining': tracker.total_races - tracker.races_completed,
            'leaderboard': leaderboard,
            'race_results': tracker.get_race_results()
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def update_tracker_margin(request):
    """Update margin for a live tracker"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        meeting = data.get('meeting', '').upper()
        margin = float(data.get('margin', 1.30))
        
        try:
            tracker = LiveTrackerState.objects.get(meeting_name=meeting)
        except LiveTrackerState.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Meeting not found'}, status=404)
        
        participants = tracker.get_participants()
        participants = _recalculate_ai_prices(participants, tracker.races_completed, margin)
        
        tracker.margin = margin
        tracker.set_participants(participants)
        tracker.save()
        
        leaderboard = _build_leaderboard(participants, margin)
        
        return JsonResponse({
            'success': True,
            'meeting': meeting,
            'margin': margin,
            'leaderboard': leaderboard
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def auto_update_tracker(request):
    """Auto update tracker - fetch latest from DB"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        meeting = data.get('meeting', '').upper()
        
        try:
            tracker = LiveTrackerState.objects.get(meeting_name=meeting)
        except LiveTrackerState.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Meeting not found'}, status=404)
        
        participants = tracker.get_participants()
        leaderboard = _build_leaderboard(participants, tracker.margin)
        
        return JsonResponse({
            'success': True,
            'meeting': tracker.meeting_name,
            'type': tracker.meeting_type,
            'margin': tracker.margin,
            'total_races': tracker.total_races,
            'races_completed': tracker.races_completed,
            'races_remaining': tracker.total_races - tracker.races_completed,
            'leaderboard': leaderboard,
            'race_results': tracker.get_race_results(),
            'updated_at': tracker.updated_at.isoformat()
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def delete_live_tracker(request, meeting_name):
    """Delete a tracker"""
    meeting = meeting_name.upper()
    
    try:
        tracker = LiveTrackerState.objects.get(meeting_name=meeting)
        tracker.is_active = False
        tracker.save()
        return JsonResponse({'success': True, 'message': f'{meeting} deactivated'})
    except LiveTrackerState.DoesNotExist:
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
    """Get meetings with results from PointsLedger"""
    from django.db.models import Sum
    days = int(request.GET.get('days', 30))
    today = date.today()
    start = today - timedelta(days=days)

    meetings = Meeting.objects.filter(date__gte=start, date__lte=today).order_by('-date', 'name')
    meeting_names = [m.name for m in meetings]

    # Fetch all trackers in one query instead of N queries
    trackers = {
        t.meeting_name: t
        for t in LiveTrackerState.objects.filter(meeting_name__in=meeting_names)
    }

    # Fetch all standings in one query per meeting_date group
    ledger_qs = (
        PointsLedger.objects
        .filter(meeting_name__in=meeting_names, meeting_date__gte=start, meeting_date__lte=today)
        .values('meeting_name', 'meeting_date', 'participant_name')
        .annotate(total_points=Sum('points_earned'))
        .order_by('meeting_name', 'meeting_date', '-total_points')
    )
    standings_map = {}
    for row in ledger_qs:
        key = (row['meeting_name'], row['meeting_date'].isoformat())
        standings_map.setdefault(key, []).append({
            'participant_name': row['participant_name'],
            'total_points': row['total_points']
        })

    history = []
    for m in meetings:
        if m.date < today:
            status = 'completed'
        elif m.date == today:
            status = 'live'
        else:
            status = 'upcoming'

        tracker = trackers.get(m.name)
        races_completed = tracker.races_completed if tracker else 0
        total_races = tracker.total_races if tracker else 8

        standings = standings_map.get((m.name, m.date.isoformat()), [])

        history.append({
            'id': m.id,
            'name': m.name,
            'date': m.date.isoformat(),
            'type': m.type,
            'country': m.country,
            'status': status,
            'races_completed': races_completed,
            'total_races': total_races,
            'standings': standings[:5],
            'winner': standings[0]['participant_name'] if standings else None,
            'winner_points': standings[0]['total_points'] if standings else 0
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
    
    # Get standings
    standings = PointsLedger.get_meeting_standings(m.name, m.date)
    
    # Get race-by-race results
    ledger_entries = PointsLedger.objects.filter(
        meeting_name=m.name,
        meeting_date=m.date
    ).order_by('race_number', 'position')
    
    races = {}
    for entry in ledger_entries:
        race_key = f"R{entry.race_number}"
        if race_key not in races:
            races[race_key] = []
        races[race_key].append({
            'participant': entry.participant_name,
            'position': entry.position,
            'points': entry.points_earned,
            'dead_heat': entry.is_dead_heat
        })
    
    # Get odds history
    odds = MeetingOdds.objects.filter(meeting=m).order_by('-timestamp')[:50]
    
    return JsonResponse({
        'success': True,
        'meeting': {
            'id': m.id, 'name': m.name, 'date': m.date.isoformat(),
            'type': m.type, 'country': m.country, 'status': m.status
        },
        'standings': standings,
        'races': races,
        'odds_history': [
            {'participant': o.participant_name, 'bookmaker': o.bookmaker, 
             'odds': o.odds, 'timestamp': o.timestamp.isoformat()} 
            for o in odds
        ]
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
    """Save meeting from scrape"""
    return JsonResponse({'success': True, 'message': 'Saved'})


@csrf_exempt
def fetch_race_results_api(request, meeting_name):
    """Fetch race results - runs Playwright in background to avoid 504 timeout"""
    meeting = meeting_name.upper()

    try:
        config = AutoFetchConfig.objects.get(meeting_name=meeting)
    except AutoFetchConfig.DoesNotExist:
        return JsonResponse({'success': False, 'error': 'Config not found'}, status=404)

    # Run heavy Playwright scraping in background thread
    # This avoids 504 timeout - server returns immediately
    import threading
    from .auto_results import fetch_and_update_meeting

    def _run_in_bg():
        from django.db import close_old_connections
        close_old_connections()  # Fresh DB connection for this thread
        try:
            result = fetch_and_update_meeting(
                meeting,
                config.get_jockeys_list(),
                config.last_race_fetched
            )
            if result.get('success'):
                config.last_fetch_at = timezone.now()
                config.last_race_fetched = result.get('last_race', config.last_race_fetched)
                config.save()
                logger.info(f"[BG Fetch] {meeting}: {result.get('new_races', 0)} new races")
        except Exception as e:
            logger.error(f"[BG Fetch] {meeting} error: {e}")
        finally:
            close_old_connections()  # Clean up after thread

    t = threading.Thread(target=_run_in_bg, daemon=True)
    t.start()

    return JsonResponse({
        'success': True,
        'message': f'Fetch started for {meeting} in background',
        'meeting': meeting,
        'last_race_before': config.last_race_fetched
    })


@csrf_exempt
def auto_fetch_standings(request, meeting_name):
    """Auto fetch standings"""
    meeting = meeting_name.upper()
    today = date.today()
    
    standings = PointsLedger.get_meeting_standings(meeting, today)
    
    return JsonResponse({
        'success': True,
        'meeting': meeting,
        'standings': standings
    })


# =====================================================
# ODDS HISTORY TRACKING
# =====================================================

def get_odds_history(request):
    """Get odds history for a meeting/participant"""
    meeting = request.GET.get('meeting', '').upper()
    participant = request.GET.get('participant', '')
    date_str = request.GET.get('date', '')
    
    if not meeting:
        return JsonResponse({'success': False, 'error': 'Meeting name required'}, status=400)
    
    query_date = None
    if date_str:
        try:
            query_date = date.fromisoformat(date_str)
        except:
            pass
    
    history = OddsSnapshot.get_odds_history(meeting, participant, query_date)
    
    by_participant = {}
    for snap in history:
        name = snap.participant_name
        if name not in by_participant:
            by_participant[name] = []
        by_participant[name].append({
            'odds': snap.odds,
            'bookmaker': snap.bookmaker,
            'captured_at': snap.captured_at.isoformat()
        })
    
    return JsonResponse({
        'success': True,
        'meeting': meeting,
        'date': (query_date or date.today()).isoformat(),
        'history': by_participant,
        'total_snapshots': history.count()
    })


def get_odds_movement(request):
    """Get odds movement (drift/firm) for participants"""
    meeting = request.GET.get('meeting', '').upper()
    
    if not meeting:
        return JsonResponse({'success': False, 'error': 'Meeting name required'}, status=400)
    
    today = date.today()
    participants = OddsSnapshot.objects.filter(
        meeting_name=meeting,
        meeting_date=today
    ).values_list('participant_name', flat=True).distinct()
    
    movements = []
    for name in participants:
        movement = OddsSnapshot.get_odds_movement(meeting, name, today)
        movement['participant'] = name
        movements.append(movement)
    
    movements.sort(key=lambda x: abs(x.get('pct_change', 0)), reverse=True)
    
    return JsonResponse({
        'success': True,
        'meeting': meeting,
        'date': today.isoformat(),
        'movements': movements
    })


def get_odds_comparison(request):
    """Compare current odds across all bookmakers"""
    meeting = request.GET.get('meeting', '').upper()

    if not meeting:
        return JsonResponse({'success': False, 'error': 'Meeting name required'}, status=400)

    today = date.today()
    from django.db.models import Max

    # Get latest timestamp per participant+bookmaker pair
    latest = OddsSnapshot.objects.filter(
        meeting_name=meeting,
        meeting_date=today
    ).values('participant_name', 'bookmaker').annotate(
        latest_time=Max('captured_at')
    )

    # Build a set of (participant, bookmaker, latest_time) to filter in one query
    from django.db.models import Q
    filters = Q()
    for item in latest:
        filters |= Q(
            participant_name=item['participant_name'],
            bookmaker=item['bookmaker'],
            captured_at=item['latest_time']
        )

    comparison = {}
    if filters:
        snaps = OddsSnapshot.objects.filter(
            meeting_name=meeting,
            meeting_date=today
        ).filter(filters)

        for snap in snaps:
            name = snap.participant_name
            if name not in comparison:
                comparison[name] = {'participant': name, 'odds': {}}
            comparison[name]['odds'][snap.bookmaker] = snap.odds

    for name, data in comparison.items():
        odds_values = list(data['odds'].values())
        if odds_values:
            data['best_odds'] = max(odds_values)
            data['worst_odds'] = min(odds_values)

    return JsonResponse({
        'success': True,
        'meeting': meeting,
        'comparison': list(comparison.values())
    })


# =====================================================
# AUTO FETCH CONTROL
# =====================================================

@csrf_exempt
def start_auto_fetch(request):
    """Start auto-fetching results for a meeting"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        meeting = data.get('meeting', '').upper()
        meeting_type = data.get('type', 'jockey')
        total_races = data.get('total_races', 8)
        interval = data.get('interval', 60)
        jockeys = data.get('jockeys', [])
        
        if not meeting:
            return JsonResponse({'success': False, 'error': 'Meeting name required'}, status=400)
        
        config, created = AutoFetchConfig.objects.update_or_create(
            meeting_name=meeting,
            defaults={
                'meeting_type': meeting_type,
                'is_enabled': True,
                'fetch_interval_seconds': interval,
                'total_races': total_races,
            }
        )
        config.set_jockeys_list(jockeys)
        config.save()
        
        return JsonResponse({
            'success': True,
            'message': f'Auto-fetch enabled for {meeting}',
            'config': {
                'meeting': meeting,
                'interval': interval,
                'total_races': total_races,
                'jockeys_count': len(jockeys)
            }
        })
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@csrf_exempt
def stop_auto_fetch(request):
    """Stop auto-fetching for a meeting"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        meeting = data.get('meeting', '').upper()
        
        config = AutoFetchConfig.objects.filter(meeting_name=meeting).first()
        if config:
            config.is_enabled = False
            config.save()
            return JsonResponse({'success': True, 'message': f'Auto-fetch stopped for {meeting}'})
        
        return JsonResponse({'success': False, 'error': 'Config not found'}, status=404)
        
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


def get_auto_fetch_status(request):
    """Get status of all auto-fetch configs"""
    configs = AutoFetchConfig.objects.all()
    
    return JsonResponse({
        'success': True,
        'configs': [{
            'meeting': c.meeting_name,
            'type': c.meeting_type,
            'enabled': c.is_enabled,
            'interval': c.fetch_interval_seconds,
            'last_fetch': c.last_fetch_at.isoformat() if c.last_fetch_at else None,
            'last_race': c.last_race_fetched,
            'total_races': c.total_races
        } for c in configs]
    })


@csrf_exempt
def trigger_auto_fetch(request):
    """Manually trigger auto-fetch - runs Playwright in background to avoid 504 timeout"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)

    try:
        data = json.loads(request.body)
        meeting = data.get('meeting', '').upper()

        if not meeting:
            return JsonResponse({'success': False, 'error': 'meeting required'}, status=400)

        config = AutoFetchConfig.objects.filter(meeting_name=meeting, is_enabled=True).first()
        if not config:
            return JsonResponse({'success': False, 'error': 'Auto-fetch not enabled for this meeting'}, status=404)

        # Run heavy Playwright scraping in background thread
        # This avoids 504 timeout - server returns immediately
        import threading
        from .auto_results import fetch_and_update_meeting

        def _run_in_bg():
            from django.db import close_old_connections
            close_old_connections()  # Fresh DB connection for this thread
            try:
                result = fetch_and_update_meeting(
                    meeting,
                    config.get_jockeys_list(),
                    config.last_race_fetched
                )
                if result.get('success'):
                    config.last_fetch_at = timezone.now()
                    config.last_race_fetched = result.get('last_race', config.last_race_fetched)
                    config.save()
                    logger.info(f"[BG AutoFetch] {meeting}: {result.get('new_races', 0)} new races")
            except Exception as e:
                logger.error(f"[BG AutoFetch] {meeting} error: {e}")
            finally:
                close_old_connections()  # Clean up after thread

        t = threading.Thread(target=_run_in_bg, daemon=True)
        t.start()

        return JsonResponse({
            'success': True,
            'message': f'Auto-fetch started for {meeting} in background',
            'meeting': meeting,
            'last_race_before': config.last_race_fetched
        })

    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# =====================================================
# POINTS LEDGER
# =====================================================

def get_points_ledger(request):
    """Get detailed points ledger for a meeting"""
    meeting = request.GET.get('meeting', '').upper()
    participant = request.GET.get('participant', '')
    
    if not meeting:
        return JsonResponse({'success': False, 'error': 'Meeting name required'}, status=400)
    
    today = date.today()
    standings = PointsLedger.get_meeting_standings(meeting, today)
    
    qs = PointsLedger.objects.filter(meeting_name=meeting, meeting_date=today)
    
    if participant:
        qs = qs.filter(participant_name__icontains=participant)
    
    races = {}
    for entry in qs.order_by('race_number'):
        race_num = f"R{entry.race_number}"
        if race_num not in races:
            races[race_num] = []
        races[race_num].append({
            'participant': entry.participant_name,
            'position': entry.position,
            'points': entry.points_earned,
            'dead_heat': entry.is_dead_heat
        })
    
    return JsonResponse({
        'success': True,
        'meeting': meeting,
        'date': today.isoformat(),
        'standings': standings,
        'races': races
    })


@csrf_exempt
def record_race_points(request):
    """Record points for a completed race"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'POST required'}, status=405)
    
    try:
        data = json.loads(request.body)
        meeting = data.get('meeting', '').upper()
        race_number = data.get('race_number', 0)
        results = data.get('results', [])
        meeting_type = data.get('type', 'jockey')
        
        if not meeting or not race_number:
            return JsonResponse({'success': False, 'error': 'Meeting and race_number required'}, status=400)
        
        today = date.today()
        points_map = {1: 3, 2: 2, 3: 1}
        
        # Detect dead heats
        position_counts = {}
        for r in results:
            pos = r.get('position', 0)
            if pos in [1, 2, 3]:
                position_counts[pos] = position_counts.get(pos, 0) + 1
        
        entries_created = []
        
        for r in results:
            jockey = r.get('jockey', r.get('driver', r.get('name', '')))
            position = r.get('position', 0)
            
            if not jockey or position not in [1, 2, 3]:
                continue
            
            num_at_position = position_counts.get(position, 1)
            is_dead_heat = num_at_position > 1
            
            if is_dead_heat:
                positions_consumed = list(range(position, min(position + num_at_position, 4)))
                total_points = sum(points_map.get(p, 0) for p in positions_consumed)
                points = round(total_points / num_at_position, 1)
            else:
                points = points_map.get(position, 0)
            
            dead_heat_with = ''
            if is_dead_heat:
                partners = [r2.get('jockey', r2.get('driver', '')) 
                           for r2 in results 
                           if r2.get('position') == position and r2.get('jockey', r2.get('driver', '')) != jockey]
                dead_heat_with = ', '.join(partners)
            
            entry, created = PointsLedger.objects.update_or_create(
                meeting_name=meeting,
                meeting_date=today,
                participant_name=jockey,
                race_number=race_number,
                defaults={
                    'participant_type': meeting_type,
                    'position': position,
                    'points_earned': points,
                    'is_dead_heat': is_dead_heat,
                    'dead_heat_with': dead_heat_with
                }
            )
            
            entries_created.append({
                'participant': jockey,
                'position': position,
                'points': points,
                'dead_heat': is_dead_heat
            })
        
        standings = PointsLedger.get_meeting_standings(meeting, today)
        
        return JsonResponse({
            'success': True,
            'meeting': meeting,
            'race': race_number,
            'entries': entries_created,
            'standings': standings
        })
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


# =====================================================
# PERSISTENT LIVE TRACKER V2 (Already using DB above)
# These are kept for URL compatibility
# =====================================================

@csrf_exempt
def init_live_tracker_persistent(request):
    """Alias for init_live_tracker - both now use DB"""
    return init_live_tracker(request)


def get_live_tracker_persistent(request, meeting_name):
    """Alias for get_live_tracker - both now use DB"""
    return get_live_tracker(request, meeting_name)