"""
ADMIN.PY - Add to your existing admin.py
Register new models for Django Admin
"""

from django.contrib import admin
from .models import Meeting, Participant, MeetingOdds, Bet
from .models import (
    GlobalState, OddsSnapshot, LiveTrackerState, 
    AutoFetchConfig, PointsLedger
)


# =====================================================
# EXISTING MODELS (if not already registered)
# =====================================================

@admin.register(Meeting)
class MeetingAdmin(admin.ModelAdmin):
    list_display = ['name', 'date', 'type', 'country', 'status']
    list_filter = ['type', 'country', 'status', 'date']
    search_fields = ['name']
    date_hierarchy = 'date'


@admin.register(Participant)
class ParticipantAdmin(admin.ModelAdmin):
    list_display = ['name', 'meeting', 'final_points', 'final_position']
    list_filter = ['meeting__type', 'meeting__date']
    search_fields = ['name', 'meeting__name']


@admin.register(MeetingOdds)
class MeetingOddsAdmin(admin.ModelAdmin):
    list_display = ['participant_name', 'meeting', 'bookmaker', 'odds', 'timestamp']
    list_filter = ['bookmaker', 'meeting']
    search_fields = ['participant_name']


@admin.register(Bet)
class BetAdmin(admin.ModelAdmin):
    list_display = ['participant', 'meeting_name', 'bookmaker', 'odds', 'stake', 'result', 'profit_loss', 'created_at']
    list_filter = ['bookmaker', 'result', 'created_at']
    search_fields = ['participant', 'meeting_name']


# =====================================================
# NEW ENHANCED MODELS
# =====================================================

@admin.register(GlobalState)
class GlobalStateAdmin(admin.ModelAdmin):
    list_display = ['key', 'updated_at', 'value_preview']
    search_fields = ['key']
    readonly_fields = ['updated_at']
    
    def value_preview(self, obj):
        """Show first 100 chars of value"""
        return obj.value[:100] + '...' if len(obj.value) > 100 else obj.value
    value_preview.short_description = 'Value Preview'


@admin.register(OddsSnapshot)
class OddsSnapshotAdmin(admin.ModelAdmin):
    list_display = ['participant_name', 'meeting_name', 'bookmaker', 'odds', 'ai_price', 'is_value', 'captured_at']
    list_filter = ['bookmaker', 'meeting_date', 'is_value', 'participant_type']
    search_fields = ['participant_name', 'meeting_name']
    date_hierarchy = 'captured_at'
    
    def get_queryset(self, request):
        # Only show today's snapshots by default
        return super().get_queryset(request).order_by('-captured_at')


@admin.register(LiveTrackerState)
class LiveTrackerStateAdmin(admin.ModelAdmin):
    list_display = ['meeting_name', 'meeting_type', 'races_completed', 'total_races', 'margin', 'is_active', 'updated_at']
    list_filter = ['meeting_type', 'is_active']
    search_fields = ['meeting_name']
    readonly_fields = ['created_at', 'updated_at']
    
    fieldsets = (
        ('Meeting Info', {
            'fields': ('meeting_name', 'meeting_type', 'is_active')
        }),
        ('Configuration', {
            'fields': ('margin', 'total_races', 'races_completed')
        }),
        ('Data', {
            'fields': ('participants_data', 'race_results_data'),
            'classes': ('collapse',)
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )


@admin.register(AutoFetchConfig)
class AutoFetchConfigAdmin(admin.ModelAdmin):
    list_display = ['meeting_name', 'meeting_type', 'is_enabled', 'fetch_interval_seconds', 
                   'last_race_fetched', 'total_races', 'last_fetch_at']
    list_filter = ['is_enabled', 'meeting_type']
    search_fields = ['meeting_name']
    list_editable = ['is_enabled', 'fetch_interval_seconds']
    
    actions = ['enable_auto_fetch', 'disable_auto_fetch']
    
    def enable_auto_fetch(self, request, queryset):
        queryset.update(is_enabled=True)
        self.message_user(request, f'{queryset.count()} configs enabled')
    enable_auto_fetch.short_description = "Enable auto-fetch"
    
    def disable_auto_fetch(self, request, queryset):
        queryset.update(is_enabled=False)
        self.message_user(request, f'{queryset.count()} configs disabled')
    disable_auto_fetch.short_description = "Disable auto-fetch"


@admin.register(PointsLedger)
class PointsLedgerAdmin(admin.ModelAdmin):
    list_display = ['participant_name', 'meeting_name', 'race_number', 'position', 
                   'points_earned', 'is_dead_heat', 'meeting_date']
    list_filter = ['meeting_date', 'participant_type', 'is_dead_heat', 'position']
    search_fields = ['participant_name', 'meeting_name']
    date_hierarchy = 'meeting_date'
    ordering = ['meeting_name', 'race_number', 'position']
    
    def get_queryset(self, request):
        # Show most recent first
        return super().get_queryset(request).select_related()


# =====================================================
# CUSTOM ADMIN VIEWS (Optional)
# =====================================================

class RacingAdminSite(admin.AdminSite):
    site_header = 'Racing AI Pricing Admin'
    site_title = 'Racing Admin'
    index_title = 'Dashboard'


# To use custom admin site, add to urls.py:
# from .admin import racing_admin_site
# path('racing-admin/', racing_admin_site.urls),

# racing_admin_site = RacingAdminSite(name='racing_admin')
# racing_admin_site.register(Meeting, MeetingAdmin)
# ... register other models