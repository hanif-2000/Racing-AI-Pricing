# racing/urls.py

from django.urls import path
from . import views

urlpatterns = [
    # Main API endpoints
    path('ai-prices/', views.get_ai_prices, name='ai_prices'),
    path('jockey-challenges/', views.get_jockey_challenges, name='jockey_challenges'),
    path('driver-challenges/', views.get_driver_challenges, name='driver_challenges'),
    path('comparison/', views.get_comparison, name='comparison'),
    path('refresh/', views.refresh_data, name='refresh'),
    
    # Bet tracker
    path('bets/', views.get_bets, name='get_bets'),
    path('bets/add/', views.add_bet, name='add_bet'),
    path('bets/update/', views.update_bet_result, name='update_bet'),
    path('bets/delete/', views.delete_bet, name='delete_bet'),
    path('bets/summary/', views.bet_summary, name='bet_summary'),
    
    # Live tracker - ORDER MATTERS! Specific paths before dynamic ones
    path('live-tracker/', views.get_all_live_trackers, name='live_trackers'),
    path('live-tracker/init/', views.init_live_tracker, name='init_live_tracker'),
    path('live-tracker/update/', views.update_race_result, name='update_race_result'),
    path('live-tracker/<str:meeting_name>/', views.get_live_tracker, name='live_tracker'),
    path('live-tracker/<str:meeting_name>/delete/', views.delete_live_tracker, name='delete_live_tracker'),
]