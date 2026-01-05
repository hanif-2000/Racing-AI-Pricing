from django.db import models

class Meeting(models.Model):
    name = models.CharField(max_length=100)
    date = models.DateField()
    type = models.CharField(max_length=20)  # jockey / driver
    country = models.CharField(max_length=5, default='AU')
    status = models.CharField(max_length=20, default='upcoming')  # upcoming/live/completed
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        unique_together = ['name', 'date', 'type']
    
    def __str__(self):
        return f"{self.name} - {self.date}"

class Participant(models.Model):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='participants')
    name = models.CharField(max_length=100)
    final_points = models.IntegerField(null=True, blank=True)
    final_position = models.IntegerField(null=True, blank=True)
    
    def __str__(self):
        return f"{self.name} @ {self.meeting.name}"

class MeetingOdds(models.Model):
    meeting = models.ForeignKey(Meeting, on_delete=models.CASCADE, related_name='odds_history')
    participant_name = models.CharField(max_length=100)
    bookmaker = models.CharField(max_length=50)
    odds = models.FloatField()
    timestamp = models.DateTimeField(auto_now_add=True)

class Bet(models.Model):
    meeting_ref = models.ForeignKey(Meeting, on_delete=models.SET_NULL, null=True, blank=True)
    meeting_name = models.CharField(max_length=100)
    participant = models.CharField(max_length=100)
    bookmaker = models.CharField(max_length=50)
    odds = models.FloatField()
    stake = models.FloatField()
    result = models.CharField(max_length=20, default='pending')
    profit_loss = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    def __str__(self):
        return f"{self.participant} @ {self.meeting_name}"
