"""
🏇 LIVE JOCKEY/DRIVER CHALLENGE TRACKER
- Tracks rides done/left after each race
- Updates points based on race results
- Calculates AI Win % and prices
- Shows race-by-race progression
"""

import asyncio
import re
from datetime import datetime


class LiveMeetingTracker:
    """Tracks a single meeting's jockey/driver challenge in real-time"""
    
    def __init__(self, meeting_name, challenge_type='jockey'):
        self.meeting = meeting_name.upper()
        self.type = challenge_type
        self.participants = {}
        self.total_races = 0
        self.races_completed = 0
        self.race_results = []
        self.bookmaker_odds = {}
        self.last_updated = None
        self.status = 'upcoming'
        
    def initialize_participants(self, participants_data, total_races=8):
        """Initialize participants from scraped odds data"""
        self.total_races = total_races
        for p in participants_data:
            name = p['name']
            self.participants[name] = {
                'rides_done': 0,
                'rides_left': total_races,
                'wins': 0,
                'seconds': 0,
                'thirds': 0,
                'points': 0,
                'last_race_points': 0,
                'history': [],
                'initial_odds': p.get('odds', 0),
                'current_odds': {},
                'ai_win_pct': 0,
                'ai_price': 0,
                'is_leader': False,
                'is_scratched': False
            }
        self.calculate_ai_prices()
        
    def add_bookmaker_odds(self, bookmaker, odds_data):
        """Add odds from a bookmaker"""
        self.bookmaker_odds[bookmaker] = {}
        for item in odds_data:
            name = item['name']
            odds = item['odds']
            self.bookmaker_odds[bookmaker][name] = odds
            if name in self.participants:
                self.participants[name]['current_odds'][bookmaker] = odds
                
    def update_race_result(self, race_num, results):
        """
        Update with race results
        results = [
            {'position': 1, 'jockey': 'James McDonald'},
            {'position': 2, 'jockey': 'Hugh Bowman'},
            {'position': 3, 'jockey': 'Blake Shinn'},
        ]
        """
        self.races_completed = race_num
        self.race_results.append({'race': race_num, 'results': results})
        
        points_map = {1: 3, 2: 2, 3: 1}
        
        race_participants = set()
        for r in results:
            jockey = r.get('jockey') or r.get('driver')
            if jockey:
                race_participants.add(jockey)
        
        for name, data in self.participants.items():
            if name in race_participants:
                data['rides_done'] += 1
                data['rides_left'] = self.total_races - data['rides_done']
                
                for r in results:
                    jockey = r.get('jockey') or r.get('driver')
                    if jockey == name:
                        pos = r['position']
                        points = points_map.get(pos, 0)
                        
                        if pos == 1:
                            data['wins'] += 1
                        elif pos == 2:
                            data['seconds'] += 1
                        elif pos == 3:
                            data['thirds'] += 1
                        
                        data['last_race_points'] = points
                        data['points'] += points
                        data['history'].append((race_num, points, data['points']))
                        break
                else:
                    data['last_race_points'] = 0
                    data['history'].append((race_num, 0, data['points']))
            else:
                data['last_race_points'] = 0
        
        self._update_leader()
        self.calculate_ai_prices()
        
        if self.races_completed >= self.total_races:
            self.status = 'completed'
        else:
            self.status = 'in_progress'
            
        self.last_updated = datetime.now().isoformat()
        
    def _update_leader(self):
        """Update who is the leader"""
        max_points = 0
        leaders = []
        
        for name, data in self.participants.items():
            if data['points'] > max_points:
                max_points = data['points']
                leaders = [name]
            elif data['points'] == max_points and max_points > 0:
                leaders.append(name)
        
        for name, data in self.participants.items():
            data['is_leader'] = name in leaders
            
    def calculate_ai_prices(self):
        """Calculate AI win probability and prices based on current standings"""
        if not self.participants:
            return
            
        points_list = [(name, data['points'], data['rides_left']) 
                       for name, data in self.participants.items() 
                       if not data['is_scratched']]
        
        if not points_list:
            return
            
        total_score = 0
        scores = {}
        
        for name, points, rides_left in points_list:
            base_score = points + 1
            opportunity = 1 + (rides_left * 0.3)
            
            data = self.participants[name]
            if data['rides_done'] > 0:
                win_rate = data['wins'] / data['rides_done']
            else:
                win_rate = 0.15
            win_factor = 1 + win_rate
            
            score = base_score * opportunity * win_factor
            scores[name] = score
            total_score += score
        
        for name, score in scores.items():
            if total_score > 0:
                win_pct = (score / total_score) * 100
                self.participants[name]['ai_win_pct'] = round(win_pct, 1)
                
                if win_pct > 0:
                    fair_price = 100 / win_pct
                    self.participants[name]['ai_price'] = round(fair_price * 0.95, 2)
                else:
                    self.participants[name]['ai_price'] = 999.0
                    
    def get_standings(self):
        """Get current standings sorted by points"""
        standings = []
        for name, data in self.participants.items():
            if data['is_scratched']:
                continue
            standings.append({
                'name': name,
                'rides_done': data['rides_done'],
                'rides_left': data['rides_left'],
                'wins': data['wins'],
                'seconds': data['seconds'],
                'thirds': data['thirds'],
                'points': data['points'],
                'last_race_points': data['last_race_points'],
                'ai_win_pct': data['ai_win_pct'],
                'ai_price': data['ai_price'],
                'is_leader': data['is_leader'],
                'current_odds': data['current_odds'],
                'history': data['history']
            })
        
        standings.sort(key=lambda x: (-x['points'], -x['wins']))
        return standings
    
    def get_race_progression_table(self):
        """Get race-by-race points progression"""
        if not self.race_results:
            return []
            
        progression = []
        for name, data in self.participants.items():
            if data['is_scratched']:
                continue
            row = {
                'name': name,
                'races': {},
                'total': data['points']
            }
            for race_num, points_gained, cumulative in data['history']:
                row['races'][f'R{race_num}'] = {
                    'gained': points_gained,
                    'cumulative': cumulative,
                    'display': f"+{points_gained} ({cumulative})" if points_gained > 0 else f"0 ({cumulative})"
                }
            progression.append(row)
        
        progression.sort(key=lambda x: -x['total'])
        return progression
    
    def get_value_bets(self, min_edge=10):
        """Find value bets where AI price is better than bookmaker odds"""
        value_bets = []
        
        for name, data in self.participants.items():
            if data['is_scratched']:
                continue
                
            ai_price = data['ai_price']
            
            for bookmaker, odds in data['current_odds'].items():
                if odds > ai_price:
                    edge = ((odds / ai_price) - 1) * 100
                    if edge >= min_edge:
                        value_bets.append({
                            'participant': name,
                            'bookmaker': bookmaker,
                            'bookmaker_odds': odds,
                            'ai_price': ai_price,
                            'edge': round(edge, 1),
                            'ai_win_pct': data['ai_win_pct']
                        })
        
        value_bets.sort(key=lambda x: -x['edge'])
        return value_bets
    
    def to_dict(self):
        """Convert to dictionary for API response"""
        return {
            'meeting': self.meeting,
            'type': self.type,
            'status': self.status,
            'total_races': self.total_races,
            'races_completed': self.races_completed,
            'last_updated': self.last_updated,
            'standings': self.get_standings(),
            'progression': self.get_race_progression_table(),
            'value_bets': self.get_value_bets(),
            'bookmakers': list(self.bookmaker_odds.keys())
        }


def create_example_tracker():
    """Create an example tracker with sample data"""
    tracker = LiveMeetingTracker('RANDWICK', 'jockey')
    
    initial_odds = [
        {'name': 'James McDonald', 'odds': 2.40},
        {'name': 'Hugh Bowman', 'odds': 3.60},
        {'name': 'Blake Shinn', 'odds': 5.80},
        {'name': 'Mark Zahra', 'odds': 8.00},
        {'name': 'Tommy Berry', 'odds': 12.00},
    ]
    tracker.initialize_participants(initial_odds, total_races=8)
    
    tracker.add_bookmaker_odds('tab', [
        {'name': 'James McDonald', 'odds': 2.50},
        {'name': 'Hugh Bowman', 'odds': 3.80},
        {'name': 'Blake Shinn', 'odds': 6.00},
        {'name': 'Mark Zahra', 'odds': 7.50},
        {'name': 'Tommy Berry', 'odds': 15.00},
    ])
    
    tracker.add_bookmaker_odds('sportsbet', [
        {'name': 'James McDonald', 'odds': 2.45},
        {'name': 'Hugh Bowman', 'odds': 3.70},
        {'name': 'Blake Shinn', 'odds': 5.50},
        {'name': 'Mark Zahra', 'odds': 8.50},
        {'name': 'Tommy Berry', 'odds': 13.00},
    ])
    
    # Simulate Race 1
    tracker.update_race_result(1, [
        {'position': 1, 'jockey': 'James McDonald'},
        {'position': 2, 'jockey': 'Hugh Bowman'},
        {'position': 3, 'jockey': 'Tommy Berry'},
        {'position': 4, 'jockey': 'Blake Shinn'},
    ])
    
    # Simulate Race 2
    tracker.update_race_result(2, [
        {'position': 1, 'jockey': 'Blake Shinn'},
        {'position': 2, 'jockey': 'James McDonald'},
        {'position': 3, 'jockey': 'Hugh Bowman'},
        {'position': 4, 'jockey': 'Mark Zahra'},
    ])
    
    # Simulate Race 3
    tracker.update_race_result(3, [
        {'position': 1, 'jockey': 'Hugh Bowman'},
        {'position': 2, 'jockey': 'Mark Zahra'},
        {'position': 3, 'jockey': 'James McDonald'},
        {'position': 4, 'jockey': 'Tommy Berry'},
    ])
    
    # Simulate Race 4
    tracker.update_race_result(4, [
        {'position': 1, 'jockey': 'James McDonald'},
        {'position': 2, 'jockey': 'Hugh Bowman'},
        {'position': 3, 'jockey': 'Mark Zahra'},
        {'position': 4, 'jockey': 'Blake Shinn'},
    ])
    
    return tracker


if __name__ == '__main__':
    tracker = create_example_tracker()
    
    print("\n" + "="*80)
    print(f"  {tracker.meeting} - JOCKEY CHALLENGE TRACKER")
    print(f"  Status: {tracker.status} | Races: {tracker.races_completed}/{tracker.total_races}")
    print("="*80)
    
    print("\n  CURRENT STANDINGS")
    print("-"*100)
    print(f"{'Jockey':<20} {'Done':>5} {'Left':>5} {'Wins':>5} {'2nds':>5} {'Pts':>5} {'Last':>6} {'AI %':>7} {'AI $':>8} {'Leader':<8}")
    print("-"*100)
    
    for s in tracker.get_standings():
        leader = "LEADER" if s['is_leader'] else ""
        last = f"+{s['last_race_points']}" if s['last_race_points'] > 0 else "0"
        print(f"{s['name']:<20} {s['rides_done']:>5} {s['rides_left']:>5} {s['wins']:>5} {s['seconds']:>5} {s['points']:>5} {last:>6} {s['ai_win_pct']:>6}% ${s['ai_price']:>7.2f} {leader}")
    
    print("\n  RACE-BY-RACE PROGRESSION")
    print("-"*80)
    header = f"{'Jockey':<20}"
    for i in range(1, tracker.races_completed + 1):
        header += f"{'R' + str(i):>12}"
    header += f"{'Total':>8}"
    print(header)
    print("-"*80)
    
    for p in tracker.get_race_progression_table():
        row = f"{p['name']:<20}"
        for i in range(1, tracker.races_completed + 1):
            race_key = f'R{i}'
            if race_key in p['races']:
                row += f"{p['races'][race_key]['display']:>12}"
            else:
                row += f"{'-':>12}"
        row += f"{p['total']:>8}"
        print(row)
    
    print("\n  VALUE BETS (Edge > 10%)")
    print("-"*70)
    value_bets = tracker.get_value_bets(min_edge=10)
    if value_bets:
        for vb in value_bets:
            print(f"  {vb['participant']}: {vb['bookmaker']} ${vb['bookmaker_odds']:.2f} vs AI ${vb['ai_price']:.2f} = {vb['edge']:.1f}% edge")
    else:
        print("  No value bets found")
    
    print("\n" + "="*80)