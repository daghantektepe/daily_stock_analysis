import React, { useEffect, useState } from 'react';
import {
  Activity,
  BarChart3,
  Bell,
  BookOpen,
  BriefcaseBusiness,
  Compass,
  Gauge,
  Home,
  LogOut,
  MessageSquareQuote,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings2,
  Sparkles,
  TrendingUp,
} from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { SCREENING_CONFIG_CHANGED_EVENT, SYSTEM_CONFIG_CHANGED_EVENT, screeningApi } from '../../api/screening';
import { useAuth } from '../../contexts/AuthContext';
import { useExperienceMode } from '../../contexts/ExperienceModeContext';
import { useAgentChatStore } from '../../stores/agentChatStore';
import { useUiLanguage } from '../../contexts/UiLanguageContext';
import type { UiTextKey } from '../../i18n/uiText';
import { cn } from '../../utils/cn';
import { ConfirmDialog } from '../common/ConfirmDialog';
import { StatusDot } from '../common/StatusDot';
import { UiLanguageToggle } from '../i18n/UiLanguageToggle';
import { ThemeToggle } from '../theme/ThemeToggle';

type SidebarNavProps = {
  collapsed?: boolean;
  onToggleCollapse?: () => void;
  onNavigate?: () => void;
  variant?: 'default' | 'rail';
};

type NavItem = {
  key: string;
  labelKey: UiTextKey;
  to: string;
  icon: React.ComponentType<{ className?: string }>;
  exact?: boolean;
  badge?: 'completion';
};

const SIMPLE_NAV_ITEMS: NavItem[] = [
  { key: 'simple', labelKey: 'layout.nav.simpleHome', to: '/simple', icon: Sparkles },
  { key: 'portfolio', labelKey: 'layout.nav.portfolio', to: '/portfolio', icon: BriefcaseBusiness },
  { key: 'chat', labelKey: 'layout.nav.chat', to: '/chat', icon: MessageSquareQuote, badge: 'completion' },
  { key: 'guide', labelKey: 'layout.nav.guide', to: '/guide', icon: BookOpen },
];

const NAV_ITEMS: NavItem[] = [
  { key: 'simple', labelKey: 'layout.nav.simpleHome', to: '/simple', icon: Sparkles },
  { key: 'home', labelKey: 'layout.nav.home', to: '/', icon: Home, exact: true },
  { key: 'chat', labelKey: 'layout.nav.chat', to: '/chat', icon: MessageSquareQuote, badge: 'completion' },
  { key: 'screening', labelKey: 'layout.nav.screening', to: '/screening', icon: Search },
  { key: 'portfolio', labelKey: 'layout.nav.portfolio', to: '/portfolio', icon: BriefcaseBusiness },
  { key: 'decision-signals', labelKey: 'layout.nav.decisionSignals', to: '/decision-signals', icon: Activity },
  { key: 'discover', labelKey: 'layout.nav.discover', to: '/discover', icon: Compass },
  { key: 'paper-trading', labelKey: 'layout.nav.paperTrading', to: '/paper-trading', icon: TrendingUp },
  { key: 'backtest', labelKey: 'layout.nav.backtest', to: '/backtest', icon: BarChart3 },
  { key: 'alerts', labelKey: 'layout.nav.alerts', to: '/alerts', icon: Bell },
  { key: 'guide', labelKey: 'layout.nav.guide', to: '/guide', icon: BookOpen },
  { key: 'usage', labelKey: 'layout.nav.usage', to: '/usage', icon: Gauge },
  { key: 'settings', labelKey: 'layout.nav.settings', to: '/settings', icon: Settings2 },
];

export const SidebarNav: React.FC<SidebarNavProps> = ({
  collapsed = false,
  onToggleCollapse,
  onNavigate,
  variant = 'default',
}) => {
  const { authEnabled, logout } = useAuth();
  const { isSimple } = useExperienceMode();
  const { t } = useUiLanguage();
  const completionBadge = useAgentChatStore((state) => state.completionBadge);
  const [showLogoutConfirm, setShowLogoutConfirm] = useState(false);
  const [showScreeningNav, setShowScreeningNav] = useState(false);

  useEffect(() => {
    let active = true;

    const refreshScreeningStatus = async () => {
      try {
        const status = await screeningApi.getStatus();
        if (active) {
          setShowScreeningNav(status.enabled);
        }
      } catch {
        if (active) {
          setShowScreeningNav(false);
        }
      }
    };

    void refreshScreeningStatus();
    window.addEventListener(SCREENING_CONFIG_CHANGED_EVENT, refreshScreeningStatus);
    window.addEventListener(SYSTEM_CONFIG_CHANGED_EVENT, refreshScreeningStatus);

    return () => {
      active = false;
      window.removeEventListener(SCREENING_CONFIG_CHANGED_EVENT, refreshScreeningStatus);
      window.removeEventListener(SYSTEM_CONFIG_CHANGED_EVENT, refreshScreeningStatus);
    };
  }, []);

  const proItems = showScreeningNav ? NAV_ITEMS : NAV_ITEMS.filter((item) => item.key !== 'screening');
  const navItems = isSimple ? SIMPLE_NAV_ITEMS : proItems;
  const isRail = variant === 'rail';
  const itemBaseClass = cn(
    'group relative flex h-[var(--nav-item-height)] w-full min-w-0 cursor-pointer items-center overflow-hidden rounded-2xl border border-transparent text-[13px] leading-tight text-secondary-text transition-all',
    collapsed
      ? 'justify-center px-0'
      : isRail
        ? 'justify-start gap-2.5 px-3'
        : 'justify-start gap-3 px-[var(--nav-item-padding-x)]'
  );
  const itemInteractiveClass = cn(
    itemBaseClass,
    'hover:bg-[var(--nav-hover-bg)] hover:text-foreground'
  );
  const itemActiveClass = 'border-[var(--nav-active-border)] bg-[var(--nav-active-bg)] font-medium text-[hsl(var(--primary))]';
  const itemIconClass = cn(isRail ? 'h-[18px] w-[18px]' : 'h-5 w-5', 'shrink-0');
  const itemLabelClass = 'min-w-0 flex-1 truncate text-left';

  return (
    <div className="flex h-full w-full min-w-0 flex-col">
      <div
        className={cn(
          'flex shrink-0 items-center',
          isRail ? 'mb-3 pt-1' : 'mb-4 px-1',
          collapsed ? 'flex-col justify-center gap-2' : 'justify-between gap-2 px-1'
        )}
      >
        <div className={cn('flex min-w-0 items-center gap-2', collapsed ? 'justify-center' : '')}>
          <div
            className={cn(
              'flex shrink-0 items-center justify-center bg-primary-gradient text-[hsl(var(--primary-foreground))] shadow-[0_12px_28px_var(--nav-brand-shadow)]',
              isRail ? 'h-9 w-9 rounded-[1rem]' : 'h-10 w-10 rounded-2xl'
            )}
          >
            <BarChart3 className={cn(isRail ? 'h-[19px] w-[19px]' : 'h-5 w-5')} />
          </div>
          {!collapsed ? (
            <p className={cn('min-w-0 truncate font-semibold text-foreground', isRail ? 'text-[0.95rem] leading-none' : 'text-sm')}>DSA</p>
          ) : null}
        </div>
        {isRail && onToggleCollapse ? (
          <button
            type="button"
            onClick={onToggleCollapse}
            aria-label={collapsed ? t('layout.expandSidebar') : t('layout.collapseSidebar')}
            className="inline-flex h-7 w-7 shrink-0 cursor-pointer items-center justify-center rounded-lg border border-transparent text-secondary-text transition-colors hover:border-border/70 hover:bg-hover hover:text-foreground"
          >
            {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </button>
        ) : null}
      </div>

      <nav className="flex min-w-0 flex-1 flex-col gap-1 overflow-y-auto overflow-x-hidden pr-0.5" aria-label={t('layout.mainNav')}>
        {navItems.map(({ key, labelKey, to, icon: Icon, exact, badge }) => {
          const label = t(labelKey);
          return (
            <NavLink
              key={key}
              to={to}
              end={exact}
              onClick={onNavigate}
              aria-label={label}
              className={({ isActive }) =>
                cn(
                  itemInteractiveClass,
                  isActive ? itemActiveClass : ''
                )
              }
            >
              {({ isActive }) => (
                <>
                  <Icon className={cn(itemIconClass, isActive ? 'text-[var(--nav-icon-active)]' : 'text-current')} />
                  {!collapsed ? <span className={itemLabelClass}>{label}</span> : null}
                  {badge === 'completion' && completionBadge ? (
                    <StatusDot
                      tone="info"
                      data-testid="chat-completion-badge"
                      className={cn(
                        'absolute right-3 border-2 border-background shadow-[0_0_10px_var(--nav-indicator-shadow)]',
                        collapsed ? 'right-2 top-2' : ''
                      )}
                      aria-label={t('layout.newChatMessage')}
                    />
                  ) : null}
                </>
              )}
            </NavLink>
          );
        })}
      </nav>

      <div className="mt-2 flex shrink-0 flex-col gap-1 border-t border-border/50 pt-2">
        <ThemeToggle
          variant={isRail ? 'rail' : 'nav'}
          collapsed={collapsed}
          wrapperClassName="w-full"
          triggerClassName={itemInteractiveClass}
          triggerActiveClassName={itemActiveClass}
          iconClassName={itemIconClass}
          labelClassName={itemLabelClass}
        />
        <UiLanguageToggle
          variant={isRail ? 'rail' : 'nav'}
          collapsed={collapsed}
          wrapperClassName="w-full"
          triggerClassName={itemInteractiveClass}
          triggerActiveClassName={itemActiveClass}
          iconClassName={itemIconClass}
          labelClassName={itemLabelClass}
        />

        {authEnabled ? (
          <button
            type="button"
            onClick={() => setShowLogoutConfirm(true)}
            className={itemInteractiveClass}
          >
            <LogOut className={itemIconClass} />
            {!collapsed ? <span className={itemLabelClass}>{t('layout.logout')}</span> : null}
          </button>
        ) : null}
      </div>

      <ConfirmDialog
        isOpen={showLogoutConfirm}
        title={t('layout.logoutTitle')}
        message={t('layout.logoutMessage')}
        confirmText={t('layout.logoutConfirm')}
        cancelText={t('common.cancel')}
        isDanger
        onConfirm={() => {
          setShowLogoutConfirm(false);
          onNavigate?.();
          void logout();
        }}
        onCancel={() => setShowLogoutConfirm(false)}
      />
    </div>
  );
};
