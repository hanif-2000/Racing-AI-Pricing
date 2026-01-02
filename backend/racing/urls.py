from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'meetings', views.MeetingViewSet)
router.register(r'bets', views.BetViewSet)

urlpatterns = [
    path('', include(router.urls)),
    path('scrape/', views.scrape_jockey_challenge, name='scrape-jockey'),
    path('scrape/jockey/', views.scrape_jockey_challenge, name='scrape-jockey'),
    path('scrape/driver/', views.scrape_driver_challenge, name='scrape-driver'),
    path('scrape/all/', views.scrape_all_challenges, name='scrape-all'),
    path('ai-prices/', views.get_ai_prices, name='ai-prices'),
    path('leaderboard/', views.get_live_leaderboard, name='leaderboard'),
    path('bet-summary/', views.bet_summary, name='bet-summary'),
    path('bet/add/', views.add_bet, name='add-bet'),
    path('bet/<int:bet_id>/update/', views.update_bet_result, name='update-bet'),
]
