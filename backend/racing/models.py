from django.db import models
from decimal import Decimal


class Meeting(models.Model):
    """Race meeting (e.g., Flemington VIC, Randwick NSW)"""
    
    MEETING_TYPES = [
        ('gallops', 'Gallops'),
        ('harness', 'Harness'),
    ]
    
    COUNTRIES = [
        ('AU', 'Australia'),
        ('NZ', 'New Zealand'),
    ]
    
    STATUS_CHOICES = [
        ('upcoming', 'Upcoming'),
        ('live', 'Live'),
        ('completed', 'Completed'),
    ]
    
    external_id = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    location = models.CharField(max_length=200)
    state = models.CharField(max_length=50)
    country = models.CharField(max_length=2, choices=COUNTRIES, default='AU')
    meeting_type = models.CharField(max_length=20, choices=MEETING_TYPES)
    date = models.DateField()
    total_races = models.PositiveIntegerField(default=0)
    completed_races = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='upcoming')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-date', 'name']
    
    def __str__(self):
        return f"{self.name} - {self.date}"


class Participant(models.Model):
    """Jockey or Driver"""
    
    PARTICIPANT_TYPES = [
        ('jockey', 'Jockey'),
        ('driver', 'Driver'),
    ]
    
    external_id = models.CharField(max_length=100, unique=True)
    name = models.CharField(max_length=200)
    participant_type = models.CharField(max_length=20, choices=PARTICIPANT_TYPES)
    total_rides = models.PositiveIntegerField(default=0)
    total_wins = models.PositiveIntegerField(default=0)
    win_percentage = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return self.name


class ChallengeEntry(models.Model):
    """Participant's entry in a meeting challenge"""
    
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='entries')
    participant = models.ForeignKey(Participant, on_delete=models.CASCADE, related_name='entries')
    total_rides = models.PositiveIntegerField(default=0)
    completed_rides = models.PositiveIntegerField(default=0)
    remaining_rides = models.PositiveIntegerField(default=0)
    points = models.DecimalField(max_digits=5, decimal_places=1, default=0)
    ai_price = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    is_winner = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        ordering = ['-points', 'ai_price']
        unique_together = ['meeting', 'participant']
    
    def __str__(self):
        return f"{self.participant.name} @ {self.meeting.name}"


class BookmakerOdds(models.Model):
    """Odds from bookmakers"""
    
    BOOKMAKERS = [
        ('tab', 'TAB'),
        ('ladbrokes', 'Ladbrokes'),
        ('sportsbet', 'Sportsbet'),
        ('tabtouch', 'TABtouch'),
        ('pointsbet', 'PointsBet'),
    ]
    
    challenge_entry = models.ForeignKey(ChallengeEntry, on_delete=models.CASCADE, related_name='odds')
    bookmaker = models.CharField(max_length=20, choices=BOOKMAKERS)
    win_odds = models.DecimalField(max_digits=8, decimal_places=2, null=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        unique_together = ['challenge_entry', 'bookmaker']
    
    def __str__(self):
        return f"{self.challenge_entry.participant.name} - {self.bookmaker}"


class Bet(models.Model):
    """User's bets"""
    
    RESULT_CHOICES = [
        ('pending', 'Pending'),
        ('win', 'Win'),
        ('loss', 'Loss'),
    ]
    
    participant_name = models.CharField(max_length=200)
    meeting_name = models.CharField(max_length=200)
    bookmaker = models.CharField(max_length=50)
    odds = models.DecimalField(max_digits=8, decimal_places=2)
    stake = models.DecimalField(max_digits=10, decimal_places=2)
    result = models.CharField(max_length=20, choices=RESULT_CHOICES, default='pending')
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.participant_name} - ${self.stake} @ {self.odds}"
    
    @property
    def profit_loss(self):
        if self.result == 'win':
            return self.stake * (self.odds - 1)
        elif self.result == 'loss':
            return -self.stake
        return Decimal('0')