from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import viewsets
from .models import Meeting, Bet
from .serializers import MeetingSerializer, BetSerializer
import asyncio


class MeetingViewSet(viewsets.ModelViewSet):
    queryset = Meeting.objects.all()
    serializer_class = MeetingSerializer


class BetViewSet(viewsets.ModelViewSet):
    queryset = Bet.objects.all().order_by('-created_at')
    serializer_class = BetSerializer


@api_view(['GET'])
def scrape_jockey_challenge(request):
    """Fetch latest jockey challenge data from TAB"""
    from .scraper import TABScraper
    
    scraper = TABScraper()
    data = asyncio.run(scraper.get_all_jockey_data())
    
    return Response({
        'success': True,
        'type': 'jockey',
        'meetings': data
    })


@api_view(['GET'])
def scrape_driver_challenge(request):
    """Fetch latest driver challenge data from TAB"""
    from .scraper import TABScraper
    
    scraper = TABScraper()
    data = asyncio.run(scraper.get_all_driver_data())
    
    return Response({
        'success': True,
        'type': 'driver',
        'meetings': data
    })


@api_view(['GET'])
def scrape_all_challenges(request):
    """Fetch all challenges (jockey + driver) from TAB"""
    from .scraper import TABScraper
    
    scraper = TABScraper()
    jockey_data = asyncio.run(scraper.get_all_jockey_data())
    driver_data = asyncio.run(scraper.get_all_driver_data())
    
    return Response({
        'success': True,
        'jockey_meetings': jockey_data,
        'driver_meetings': driver_data,
        'total_meetings': len(jockey_data) + len(driver_data)
    })


@api_view(['GET'])
def get_ai_prices(request):
    """Calculate AI prices for all challenges"""
    from .scraper import TABScraper
    
    scraper = TABScraper()
    jockey_data = asyncio.run(scraper.get_all_jockey_data())
    driver_data = asyncio.run(scraper.get_all_driver_data())
    
    market_percentage = float(request.GET.get('market', 130))
    
    def calculate_ai_prices(meetings):
        result = []
        for meeting in meetings:
            participants = meeting.get('jockeys', [])
            if not participants:
                continue
                
            total_implied_prob = sum(1 / p['odds'] for p in participants)
            
            enhanced_participants = []
            for p in participants:
                implied_prob = 1 / p['odds']
                fair_prob = implied_prob / total_implied_prob
                ai_price = round((1 / fair_prob) * (market_percentage / 100), 2)
                
                enhanced_participants.append({
                    'name': p['name'],
                    'tab_odds': p['odds'],
                    'ai_price': ai_price,
                    'implied_prob': round(implied_prob * 100, 1),
                    'fair_prob': round(fair_prob * 100, 1),
                    'value': 'YES' if p['odds'] > ai_price else 'NO',
                    'edge': round(((p['odds'] - ai_price) / ai_price) * 100, 1)
                })
            
            result.append({
                'meeting': meeting['meeting'],
                'type': meeting.get('type', 'jockey'),
                'participants': enhanced_participants,
                'total_participants': len(enhanced_participants)
            })
        
        return result
    
    jockey_prices = calculate_ai_prices(jockey_data)
    driver_prices = calculate_ai_prices(driver_data)
    
    # Count value bets
    total_value_bets = 0
    for m in jockey_prices + driver_prices:
        total_value_bets += sum(1 for p in m['participants'] if p['value'] == 'YES')
    
    return Response({
        'success': True,
        'market_percentage': market_percentage,
        'jockey_challenges': jockey_prices,
        'driver_challenges': driver_prices,
        'summary': {
            'total_jockey_meetings': len(jockey_prices),
            'total_driver_meetings': len(driver_prices),
            'total_value_bets': total_value_bets
        }
    })


@api_view(['GET'])
def get_live_leaderboard(request):
    """Get live leaderboard with points for a meeting"""
    meeting_name = request.GET.get('meeting', '')
    
    return Response({
        'success': True,
        'meeting': meeting_name,
        'leaderboard': [],
        'message': 'Live results integration coming soon'
    })


@api_view(['GET'])
def bet_summary(request):
    """Get betting summary with filters"""
    bookmaker = request.GET.get('bookmaker', None)
    meeting = request.GET.get('meeting', None)
    period = request.GET.get('period', 'all')
    
    bets = Bet.objects.all()
    
    if bookmaker:
        bets = bets.filter(bookmaker=bookmaker)
    if meeting:
        bets = bets.filter(meeting__icontains=meeting)
    
    total_staked = sum(b.stake for b in bets)
    total_won = sum(b.stake * b.odds for b in bets.filter(result='win'))
    total_lost = sum(b.stake for b in bets.filter(result='loss'))
    pending = bets.filter(result='pending').count()
    settled = bets.exclude(result='pending').count()
    wins = bets.filter(result='win').count()
    
    return Response({
        'total_bets': bets.count(),
        'total_staked': total_staked,
        'total_won': total_won,
        'total_lost': total_lost,
        'net_profit': total_won - total_staked,
        'pending': pending,
        'settled': settled,
        'wins': wins,
        'win_rate': round((wins / settled * 100), 1) if settled > 0 else 0
    })


@api_view(['POST'])
def add_bet(request):
    """Add a new bet"""
    data = request.data
    
    bet = Bet.objects.create(
        jockey_driver=data.get('participant', ''),
        meeting=data.get('meeting', ''),
        bookmaker=data.get('bookmaker', 'TAB'),
        odds=data.get('odds', 0),
        stake=data.get('stake', 0),
        bet_type=data.get('type', 'jockey'),
        result='pending'
    )
    
    return Response({
        'success': True,
        'bet_id': bet.id,
        'message': 'Bet added successfully'
    })


@api_view(['PUT'])
def update_bet_result(request, bet_id):
    """Update bet result (win/loss)"""
    try:
        bet = Bet.objects.get(id=bet_id)
        bet.result = request.data.get('result', 'pending')
        bet.save()
        
        return Response({
            'success': True,
            'message': 'Bet updated successfully'
        })
    except Bet.DoesNotExist:
        return Response({
            'success': False,
            'message': 'Bet not found'
        }, status=404)
