"""
Live Meeting Tracker - Track points during live meetings
Points: 1st=3, 2nd=2, 3rd=1
Dead heat: Split points (e.g., dead heat 3rd = 0.5 each)
"""

from datetime import datetime
from typing import Dict, List, Optional


class LiveMeetingTracker:
    def __init__(self, meeting_name: str, meeting_type: str = 'jockey', margin: float = 1.30):
        self.meeting_name = meeting_name.upper()
        self.meeting_type = meeting_type  # 'jockey' or 'driver'
        self.margin = margin  # Adjustable margin (default 130%)
        self.participants: Dict[str, dict] = {}
        self.total_races = 0
        self.races_completed = 0
        self.race_results: List[dict] = []
        self.created_at = datetime.now()
        self.updated_at = datetime.now()
    
    def set_margin(self, margin: float):
        """Update margin and recalculate prices"""
        self.margin = margin
        self._recalculate_ai_prices()
    
    def initialize_participants(self, participants: List[dict], total_races: int = 8):
        """Initialize participants with their starting odds"""
        self.total_races = total_races
        self.participants = {}
        
        for p in participants:
            name = p.get('name', '')
            self.participants[name] = {
                'name': name,
                'starting_odds': p.get('odds', 0),
                'current_points': 0,
                'rides_total': total_races,
                'rides_remaining': total_races,
                'positions': [],  # List of positions per race
                'points_history': [],  # Points earned per race
                'ai_price': 0,
                'value': 'NO'
            }
        
        self._recalculate_ai_prices()
    
    def update_race_result(self, race_num: int, results: List[dict]):
        """
        Update with race result
        results = [{'position': 1, 'jockey': 'Name'}, ...]
        
        Points System:
        - 1st place: 3 points
        - 2nd place: 2 points  
        - 3rd place: 1 point
        
        Dead Heat Rules:
        - Dead heat 1st (2 runners): (3+2)/2 = 2.5 each
        - Dead heat 2nd (2 runners): (2+1)/2 = 1.5 each
        - Dead heat 3rd (2 runners): 1/2 = 0.5 each
        - Dead heat 1st (3 runners): (3+2+1)/3 = 2.0 each
        """
        if race_num <= self.races_completed:
            return  # Already processed this race
        
        # Count runners at each position (for dead heat detection)
        position_counts = {}
        for r in results:
            pos = r.get('position', 0)
            if pos in [1, 2, 3]:
                position_counts[pos] = position_counts.get(pos, 0) + 1
        
        # Base points for positions
        points_map = {1: 3, 2: 2, 3: 1}
        
        # Track who got points this race
        participants_in_race = set()
        
        for r in results:
            jockey = r.get('jockey', r.get('driver', r.get('name', '')))
            position = r.get('position', 0)
            
            if jockey in self.participants and position in [1, 2, 3]:
                participants_in_race.add(jockey)
                
                # Calculate points with dead heat handling
                num_at_position = position_counts.get(position, 1)
                
                if num_at_position > 1:
                    # DEAD HEAT - Split the points that would be awarded
                    # E.g., 2 dead heat for 1st: positions 1 and 2 are taken
                    # Total points = 3 (1st) + 2 (2nd) = 5, split = 2.5 each
                    
                    # Calculate which positions are "consumed" by dead heat
                    positions_consumed = list(range(position, min(position + num_at_position, 4)))
                    total_points = sum(points_map.get(p, 0) for p in positions_consumed)
                    points = total_points / num_at_position
                else:
                    points = points_map.get(position, 0)
                
                # Round to 1 decimal for clean 0.5 values
                points = round(points, 1)
                
                self.participants[jockey]['current_points'] += points
                self.participants[jockey]['positions'].append(position)
                self.participants[jockey]['points_history'].append(points)
                self.participants[jockey]['rides_remaining'] -= 1
        
        # Mark non-placed participants as having completed a ride (0 points)
        for name, data in self.participants.items():
            if name not in participants_in_race and data['rides_remaining'] > 0:
                data['rides_remaining'] -= 1
                data['positions'].append(0)  # 0 = unplaced
                data['points_history'].append(0)
        
        self.races_completed = race_num
        self.race_results.append({
            'race': race_num,
            'results': results,
            'dead_heats': {pos: count for pos, count in position_counts.items() if count > 1},
            'timestamp': datetime.now().isoformat()
        })
        
        self._recalculate_ai_prices()
        self.updated_at = datetime.now()
    
    def _recalculate_ai_prices(self):
        """Recalculate AI prices based on current standings with adjustable margin"""
        if not self.participants:
            return
        
        standings = []
        for name, data in self.participants.items():
            current_points = data['current_points']
            races_done = self.races_completed
            rides_remaining = data['rides_remaining']
            
            if races_done > 0:
                # Average points per race
                avg_points = current_points / races_done
                estimated_final = current_points + (avg_points * rides_remaining)
            else:
                # Use starting odds to estimate
                estimated_final = 1 / data['starting_odds'] if data['starting_odds'] > 0 else 0
            
            standings.append({
                'name': name,
                'current_points': current_points,
                'estimated_final': estimated_final,
                'probability': 0
            })
        
        # Sort by current points (descending)
        standings.sort(key=lambda x: (-x['current_points'], -x['estimated_final']))
        
        # Calculate probabilities
        total_estimated = sum(s['estimated_final'] for s in standings) or 1
        
        for s in standings:
            s['probability'] = (s['estimated_final'] / total_estimated) * 100
        
        # Update participants with AI prices using adjustable margin
        for s in standings:
            name = s['name']
            prob = s['probability']
            
            if prob > 0:
                fair_price = 100 / prob
                ai_price = fair_price * self.margin  # Use adjustable margin
            else:
                ai_price = 999
            
            self.participants[name]['ai_price'] = round(ai_price, 2)
            self.participants[name]['value'] = 'YES' if self.participants[name]['starting_odds'] > ai_price else 'NO'
    
    def get_leaderboard(self) -> List[dict]:
        """Get current leaderboard sorted by points"""
        leaderboard = []
        for name, data in self.participants.items():
            leaderboard.append({
                'name': name,
                'points': data['current_points'],
                'rides_remaining': data['rides_remaining'],
                'rides_total': data['rides_total'],
                'starting_odds': data['starting_odds'],
                'ai_price': data['ai_price'],
                'value': data['value'],
                'positions': data['positions'],
                'points_history': data.get('points_history', [])
            })
        
        leaderboard.sort(key=lambda x: (-x['points'], x['ai_price']))
        
        # Add rank
        for i, item in enumerate(leaderboard):
            item['rank'] = i + 1
        
        return leaderboard
    
    def to_dict(self) -> dict:
        """Convert tracker to dictionary for API response"""
        return {
            'meeting': self.meeting_name,
            'type': self.meeting_type,
            'margin': self.margin,
            'total_races': self.total_races,
            'races_completed': self.races_completed,
            'races_remaining': self.total_races - self.races_completed,
            'leaderboard': self.get_leaderboard(),
            'race_results': self.race_results,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat()
        }


# Dead Heat Examples:
# ------------------
# Dead heat 1st (2 runners): 
#   Positions consumed: 1, 2
#   Total points: 3 + 2 = 5
#   Each gets: 5 / 2 = 2.5 points
#
# Dead heat 2nd (2 runners):
#   Positions consumed: 2, 3
#   Total points: 2 + 1 = 3
#   Each gets: 3 / 2 = 1.5 points
#
# Dead heat 3rd (2 runners):
#   Positions consumed: 3 (only 3rd pays)
#   Total points: 1
#   Each gets: 1 / 2 = 0.5 points
#
# Dead heat 1st (3 runners):
#   Positions consumed: 1, 2, 3
#   Total points: 3 + 2 + 1 = 6
#   Each gets: 6 / 3 = 2.0 points