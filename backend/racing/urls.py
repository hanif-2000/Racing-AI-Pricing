from django.urls import path
from . import views

urlpatterns = [
    # Main API
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
    
    # Live tracker
    path('live-tracker/', views.get_all_live_trackers, name='live_trackers'),
    path('live-tracker/init/', views.init_live_tracker, name='init_live_tracker'),
    path('live-tracker/update/', views.update_race_result, name='update_race_result'),
    path('live-tracker/margin/', views.update_tracker_margin, name='update_margin'),
    path('live-tracker/auto-update/', views.auto_update_tracker, name='auto_update'),
    path('live-tracker/<str:meeting_name>/', views.get_live_tracker, name='live_tracker'),
    path('live-tracker/<str:meeting_name>/delete/', views.delete_live_tracker, name='delete_live_tracker'),
    
    # Calendar & History
    path('calendar/', views.calendar_view, name='calendar'),
    path('history/', views.history_view, name='history'),
    path('meeting/<int:meeting_id>/', views.meeting_detail, name='meeting_detail'),
    path('meeting/<int:meeting_id>/result/', views.save_meeting_result, name='save_result'),
    path('meeting/save/', views.save_meeting_from_scrape, name='save_meeting'),
    
    # Auto Results
    path('results/<str:meeting_name>/', views.fetch_race_results_api, name='fetch_results'),
    path('auto-standings/<str:meeting_name>/', views.auto_fetch_standings, name='auto_standings'),
]