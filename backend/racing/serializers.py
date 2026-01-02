from rest_framework import serializers
from .models import Meeting, Participant, ChallengeEntry, BookmakerOdds, Bet


class BookmakerOddsSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookmakerOdds
        fields = ['bookmaker', 'win_odds']


class ParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Participant
        fields = ['id', 'name', 'participant_type', 'win_percentage']


class ChallengeEntrySerializer(serializers.ModelSerializer):
    participant = ParticipantSerializer(read_only=True)
    odds = BookmakerOddsSerializer(many=True, read_only=True)
    
    class Meta:
        model = ChallengeEntry
        fields = ['id', 'participant', 'total_rides', 'completed_rides', 
                  'remaining_rides', 'points', 'ai_price', 'odds']


class MeetingSerializer(serializers.ModelSerializer):
    entries = ChallengeEntrySerializer(many=True, read_only=True)
    
    class Meta:
        model = Meeting
        fields = ['id', 'name', 'location', 'state', 'country', 
                  'meeting_type', 'date', 'status', 'total_races', 
                  'completed_races', 'entries']


class MeetingListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Meeting
        fields = ['id', 'name', 'location', 'meeting_type', 'date', 'status']


class BetSerializer(serializers.ModelSerializer):
    profit_loss = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)
    
    class Meta:
        model = Bet
        fields = ['id', 'participant_name', 'meeting_name', 'bookmaker', 
                  'odds', 'stake', 'result', 'profit_loss', 'created_at']