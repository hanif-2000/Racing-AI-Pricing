from django.db import models


class Meeting(models.Model):
    name = models.CharField(max_length=100, db_index=True)
    date = models.DateField(db_index=True)
    type = models.CharField(max_length=20)  # jockey / driver
    country = models.CharField(max_length=5, default='AU', db_index=True)
    status = models.CharField(max_length=20, default='upcoming')  # upcoming/live/completed
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