"""
RACING MODELS - Complete with Enhanced Features
- Original models (Meeting, Participant, MeetingOdds, Bet)
- GlobalState: Persistent scraped data storage
- OddsSnapshot: Historical odds tracking  
- LiveTrackerState: Persistent live trackers
- AutoFetchConfig: Auto results configuration
- PointsLedger: Detailed points tracking
"""

from django.db import models
from django.utils import timezone
import json

class Meeting(models.Model):
    name = models.CharField(max_length=100, db_index=True)
    date = models.DateField(db_index=True)
    type = models.CharField(max_length=20)  
    country = models.CharField(max_length=5, default='AU', db_index=True)
    status = models.CharField(max_length=20, default='upcoming') 
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['name', 'date', 'type']
        ordering = ['-date', 'name']
    
    def __str__(self):
        return f"{self.name} - {self.date} ({self.type})"


class Participant(models.Model):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='participants')
    name = models.CharField(max_length=100, db_index=True)
    final_points = models.IntegerField(null=True, blank=True)
    final_position = models.IntegerField(null=True, blank=True)
    
    class Meta:
        unique_together = ['meeting', 'name']
    
    def __str__(self):
        return f"{self.name} @ {self.meeting.name}"


class MeetingOdds(models.Model):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='odds_history')
    participant_name = models.CharField(max_length=100, db_index=True)
    bookmaker = models.CharField(max_length=50, db_index=True)
    odds = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-timestamp']
    
    def __str__(self):
        return f"{self.participant_name} @ {self.bookmaker}: {self.odds}"


class Bet(models.Model):
    meeting_ref = models.ForeignKey(Meeting, on_delete=models.SET_NULL, null=True, blank=True)
    meeting_name = models.CharField(max_length=100)
    participant = models.CharField(max_length=100)
    bookmaker = models.CharField(max_length=50)
    odds = models.FloatField()
    stake = models.FloatField()
    result = models.CharField(max_length=20, default='pending', db_index=True)
    profit_loss = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.participant} @ {self.meeting_name} - {self.result}"

class GlobalState(models.Model):
    """
    Stores scraped data persistently in database
    Replaces in-memory SCRAPED_DATA dictionary
    """
    key = models.CharField(max_length=100, unique=True, db_index=True)
    value = models.TextField() 
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        verbose_name = "Global State"
        verbose_name_plural = "Global States"
    
    def __str__(self):
        return f"{self.key} (updated: {self.updated_at})"
    
    @classmethod
    def set_value(cls, key, data):
        """Save data to database"""
        json_data = json.dumps(data, default=str)
        obj, created = cls.objects.update_or_create(
            key=key,
            defaults={'value': json_data}
        )
        return obj
    
    @classmethod
    def get_value(cls, key, default=None):
        """Retrieve data from database"""
        try:
            obj = cls.objects.get(key=key)
            return json.loads(obj.value)
        except cls.DoesNotExist:
            return default
    
    @classmethod
    def get_last_updated(cls, key):
        """Get last update timestamp"""
        try:
            obj = cls.objects.get(key=key)
            return obj.updated_at
        except cls.DoesNotExist:
            return None


class ScrapedDataManager:
    """
    Manager class to handle scraped data storage
    Drop-in replacement for global SCRAPED_DATA dict
    
    Usage:
        # Save data
        ScrapedDataManager.save_scraped_data(jockey_list, driver_list)
        
        # Get data
        data = ScrapedDataManager.get_scraped_data()
    """
    
    KEY_JOCKEY = 'jockey_challenges'
    KEY_DRIVER = 'driver_challenges'
    KEY_LAST_UPDATED = 'scrape_last_updated'
    
    @classmethod
    def save_scraped_data(cls, jockey_challenges, driver_challenges):
        """Save all scraped data to database"""
        GlobalState.set_value(cls.KEY_JOCKEY, jockey_challenges)
        GlobalState.set_value(cls.KEY_DRIVER, driver_challenges)
        GlobalState.set_value(cls.KEY_LAST_UPDATED, timezone.now().isoformat())
        
        # Also save odds history
        cls._save_odds_history(jockey_challenges, 'jockey')
        cls._save_odds_history(driver_challenges, 'driver')
    
    @classmethod
    def get_scraped_data(cls):
        """Get all scraped data from database"""
        return {
            'jockey_challenges': GlobalState.get_value(cls.KEY_JOCKEY, []),
            'driver_challenges': GlobalState.get_value(cls.KEY_DRIVER, []),
            'last_updated': GlobalState.get_value(cls.KEY_LAST_UPDATED)
        }
    
    @classmethod
    def _save_odds_history(cls, challenges, challenge_type):
        """Save odds to history for tracking"""
        from datetime import date
        today = date.today()
        
        for meeting_data in challenges:
            meeting_name = meeting_data.get('meeting', '').upper()
            source = meeting_data.get('source', 'unknown')
            
            participants_key = 'jockeys' if challenge_type == 'jockey' else 'drivers'
            participants = meeting_data.get(participants_key, [])
            
            for p in participants:
                name = p.get('name', '')
                odds = p.get('odds', 0)
                
                if name and odds > 0:
                    OddsSnapshot.objects.create(
                        meeting_name=meeting_name,
                        meeting_date=today,
                        participant_name=name,
                        participant_type=challenge_type,
                        bookmaker=source,
                        odds=odds
                    )

class OddsSnapshot(models.Model):
    """
    Stores historical odds for each participant
    Tracks how odds change throughout the day
    
    Usage:
        # Get odds history
        history = OddsSnapshot.get_odds_history('FLEMINGTON', 'Jamie Kah')
        
        # Get odds movement
        movement = OddsSnapshot.get_odds_movement('FLEMINGTON', 'Jamie Kah')
        # Returns: {'movement': 'firming', 'change': -0.5, 'opening': 3.5, 'current': 3.0}
    """
    meeting_name = models.CharField(max_length=100, db_index=True)
    meeting_date = models.DateField(db_index=True)
    participant_name = models.CharField(max_length=100, db_index=True)
    participant_type = models.CharField(max_length=20) 
    bookmaker = models.CharField(max_length=50, db_index=True)
    odds = models.FloatField()
    ai_price = models.FloatField(null=True, blank=True)
    is_value = models.BooleanField(default=False)
    captured_at = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-captured_at']
        indexes = [
            models.Index(fields=['meeting_name', 'meeting_date']),
            models.Index(fields=['participant_name', 'meeting_date']),
            models.Index(fields=['bookmaker', 'captured_at']),
        ]
    
    def __str__(self):
        return f"{self.participant_name} @ {self.meeting_name}: {self.odds} ({self.bookmaker})"
    
    @classmethod
    def get_odds_history(cls, meeting_name, participant_name=None, query_date=None):
        """Get odds history for a meeting/participant"""
        from datetime import date as date_class
        
        qs = cls.objects.filter(meeting_name=meeting_name.upper())
        
        if query_date:
            qs = qs.filter(meeting_date=query_date)
        else:
            qs = qs.filter(meeting_date=date_class.today())
        
        if participant_name:
            qs = qs.filter(participant_name__icontains=participant_name)
        
        return qs.order_by('captured_at')
    
    @classmethod
    def get_opening_odds(cls, meeting_name, participant_name, query_date=None):
        """Get first recorded odds of the day"""
        history = cls.get_odds_history(meeting_name, participant_name, query_date)
        return history.first()
    
    @classmethod
    def get_odds_movement(cls, meeting_name, participant_name, query_date=None):
        """
        Calculate odds movement (drift/firm)
        
        Returns:
            {
                'movement': 'firming' | 'drifting' | 'stable',
                'change': float,
                'pct_change': float,
                'opening': float,
                'current': float,
                'snapshots': int
            }
        """
        history = cls.get_odds_history(meeting_name, participant_name, query_date)
        
        if history.count() < 2:
            return {'movement': 'stable', 'change': 0, 'pct_change': 0}
        
        first = history.first()
        last = history.last()
        
        change = last.odds - first.odds
        pct_change = (change / first.odds) * 100 if first.odds > 0 else 0
        
        if change > 0.5:
            movement = 'drifting'
        elif change < -0.5:
            movement = 'firming' 
        else:
            movement = 'stable'
        
        return {
            'movement': movement,
            'change': round(change, 2),
            'pct_change': round(pct_change, 1),
            'opening': first.odds,
            'current': last.odds,
            'snapshots': history.count()
        }

class LiveTrackerState(models.Model):
    """
    Stores live tracker data in database
    Replaces in-memory LIVE_TRACKERS dictionary
    Data survives server restarts
    """
    meeting_name = models.CharField(max_length=100, unique=True, db_index=True)
    meeting_type = models.CharField(max_length=20) 
    margin = models.FloatField(default=1.30)
    total_races = models.IntegerField(default=8)
    races_completed = models.IntegerField(default=0)
    participants_data = models.TextField()
    race_results_data = models.TextField(default='[]')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Live Tracker"
        verbose_name_plural = "Live Trackers"
    
    def __str__(self):
        return f"{self.meeting_name} ({self.meeting_type}) - R{self.races_completed}/{self.total_races}"
    
    def get_participants(self):
        """Get participants dict from JSON"""
        return json.loads(self.participants_data)
    
    def set_participants(self, data):
        """Save participants dict as JSON"""
        self.participants_data = json.dumps(data)
    
    def get_race_results(self):
        """Get race results list from JSON"""
        return json.loads(self.race_results_data)
    
    def add_race_result(self, result):
        """Add a race result to the list"""
        results = self.get_race_results()
        results.append(result)
        self.race_results_data = json.dumps(results, default=str)

class AutoFetchConfig(models.Model):
    """
    Configuration for automatic results fetching
    
    Usage:
        # Create config
        config = AutoFetchConfig.objects.create(
            meeting_name='FLEMINGTON',
            meeting_type='jockey',
            total_races=8,
            fetch_interval_seconds=60
        )
        config.set_jockeys_list(['Jamie Kah', 'Damien Oliver'])
        config.save()
    """
    meeting_name = models.CharField(max_length=100, unique=True, db_index=True)
    meeting_type = models.CharField(max_length=20)
    is_enabled = models.BooleanField(default=True)
    fetch_interval_seconds = models.IntegerField(default=60) 
    last_fetch_at = models.DateTimeField(null=True, blank=True)
    last_race_fetched = models.IntegerField(default=0)
    total_races = models.IntegerField(default=8)
    jockeys_list = models.TextField(default='[]') 
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-created_at']
        verbose_name = "Auto Fetch Config"
        verbose_name_plural = "Auto Fetch Configs"
    
    def __str__(self):
        status = "🟢" if self.is_enabled else "🔴"
        return f"{status} {self.meeting_name} - R{self.last_race_fetched}/{self.total_races}"
    
    def get_jockeys_list(self):
        """Get jockeys list from JSON"""
        return json.loads(self.jockeys_list)
    
    def set_jockeys_list(self, jockeys):
        """Save jockeys list as JSON"""
        self.jockeys_list = json.dumps(jockeys)

class PointsLedger(models.Model):
    """
    Detailed points tracking for each participant per race
    
    Points System:
        1st = 3 points
        2nd = 2 points
        3rd = 1 point
        
    Dead Heat:
        Dead heat 1st (2 runners): (3+2)/2 = 2.5 each
        Dead heat 2nd (2 runners): (2+1)/2 = 1.5 each
        Dead heat 3rd (2 runners): 1/2 = 0.5 each
    
    Usage:
        # Get standings
        standings = PointsLedger.get_meeting_standings('FLEMINGTON')
        
        # Get participant history
        history = PointsLedger.get_participant_history('FLEMINGTON', 'Jamie Kah')
    """
    meeting_name = models.CharField(max_length=100, db_index=True)
    meeting_date = models.DateField(db_index=True)
    participant_name = models.CharField(max_length=100, db_index=True)
    participant_type = models.CharField(max_length=20)  
    race_number = models.IntegerField()
    position = models.IntegerField() 
    points_earned = models.FloatField()
    is_dead_heat = models.BooleanField(default=False)
    dead_heat_with = models.CharField(max_length=200, blank=True) 
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['meeting_name', 'race_number', 'position']
        unique_together = ['meeting_name', 'meeting_date', 'participant_name', 'race_number']
        indexes = [
            models.Index(fields=['meeting_name', 'meeting_date']),
            models.Index(fields=['participant_name', 'meeting_date']),
        ]
        verbose_name = "Points Ledger Entry"
        verbose_name_plural = "Points Ledger"
    
    def __str__(self):
        pos_str = f"P{self.position}" if self.position > 0 else "DNP"
        dh = " (DH)" if self.is_dead_heat else ""
        return f"{self.participant_name} R{self.race_number}: {pos_str}{dh} +{self.points_earned}"
    
    @classmethod
    def get_meeting_standings(cls, meeting_name, query_date=None):
        """
        Get current standings for a meeting
        
        Returns:
            [
                {'participant_name': 'Jamie Kah', 'total_points': 12.5},
                {'participant_name': 'Damien Oliver', 'total_points': 8.0},
                ...
            ]
        """
        from datetime import date as date_class
        from django.db.models import Sum
        
        if not query_date:
            query_date = date_class.today()
        
        standings = cls.objects.filter(
            meeting_name=meeting_name.upper(),
            meeting_date=query_date
        ).values('participant_name').annotate(
            total_points=Sum('points_earned')
        ).order_by('-total_points')
        
        return list(standings)
    
    @classmethod
    def get_participant_history(cls, meeting_name, participant_name, query_date=None):
        """
        Get race-by-race history for a participant
        
        Returns QuerySet of PointsLedger entries
        """
        from datetime import date as date_class
        
        if not query_date:
            query_date = date_class.today()
        
        return cls.objects.filter(
            meeting_name=meeting_name.upper(),
            participant_name__icontains=participant_name,
            meeting_date=query_date
        ).order_by('race_number')
    
    @classmethod
    def record_race_result(cls, meeting_name, meeting_date, race_number, results, meeting_type='jockey'):
        """
        Record points for a race
        
        Args:
            meeting_name: str
            meeting_date: date
            race_number: int
            results: list of {'position': int, 'jockey': str}
            meeting_type: 'jockey' or 'driver'
        
        Returns:
            list of created entries
        """
        points_map = {1: 3, 2: 2, 3: 1}
        position_counts = {}
        for r in results:
            pos = r.get('position', 0)
            if pos in [1, 2, 3]:
                position_counts[pos] = position_counts.get(pos, 0) + 1
        
        entries = []
        
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
            entry, created = cls.objects.update_or_create(
                meeting_name=meeting_name.upper(),
                meeting_date=meeting_date,
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
            
            entries.append(entry)
        
        return entries