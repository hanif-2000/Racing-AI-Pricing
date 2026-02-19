from rest_framework import serializers
from .models import Meeting, Participant, MeetingOdds, Bet


class MeetingOddsSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeetingOdds
        fields = ['bookmaker', 'odds', 'timestamp']


class ParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = Participant
        fields = ['id', 'name', 'final_points', 'final_position']


class MeetingSerializer(serializers.ModelSerializer):
    participants = ParticipantSerializer(many=True, read_only=True)

    class Meta:
        model = Meeting
        fields = ['id', 'name', 'date', 'type', 'country', 'status', 'participants']


class MeetingListSerializer(serializers.ModelSerializer):
    class Meta:
        model = Meeting
        fields = ['id', 'name', 'date', 'type', 'country', 'status']


class BetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bet
        fields = ['id', 'participant', 'meeting_name', 'bookmaker',
                  'odds', 'stake', 'result', 'profit_loss', 'created_at']