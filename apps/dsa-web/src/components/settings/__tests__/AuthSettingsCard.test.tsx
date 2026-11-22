import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { AuthSettingsCard } from '../AuthSettingsCard';

const { refreshStatus, updateSettings, useAuthMock } = vi.hoisted(() => ({
  refreshStatus: vi.fn(),
  updateSettings: vi.fn(),
  useAuthMock: vi.fn(),
}));

vi.mock('../../../hooks', () => ({
  useAuth: () => useAuthMock(),
}));

vi.mock('../../../api/auth', () => ({
  authApi: {
    updateSettings,
  },
}));

describe('AuthSettingsCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthMock.mockReturnValue({
      authEnabled: false,
      setupState: 'no_password',
      refreshStatus,
    });
  });

  it('enables auth with a new password and refreshes status', async () => {
    updateSettings.mockResolvedValue(undefined);
    refreshStatus.mockResolvedValue(undefined);

    render(<AuthSettingsCard />);

    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.change(screen.getByLabelText('Set admin password'), { target: { value: 'passwd6' } });
    fireEvent.change(screen.getByLabelText('Confirm new password'), { target: { value: 'passwd6' } });
    fireEvent.click(screen.getByRole('button', { name: 'Enable authentication' }));

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith(true, 'passwd6', 'passwd6', undefined);
    });
    expect(refreshStatus).toHaveBeenCalled();
    expect(await screen.findByText('Authentication settings updated')).toBeInTheDocument();
  });

  it('blocks disabling auth when the current admin password is missing (Issue #1970)', async () => {
    useAuthMock.mockReturnValue({
      authEnabled: true,
      setupState: 'enabled',
      refreshStatus,
    });
    updateSettings.mockResolvedValue(undefined);
    refreshStatus.mockResolvedValue(undefined);

    render(<AuthSettingsCard />);

    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Disable authentication' }));

    expect(await screen.findByText('Current admin password is required before disabling authentication')).toBeInTheDocument();
    expect(updateSettings).not.toHaveBeenCalled();
  });

  it('disables auth when the current admin password is provided (Issue #1970)', async () => {
    useAuthMock.mockReturnValue({
      authEnabled: true,
      setupState: 'enabled',
      refreshStatus,
    });
    updateSettings.mockResolvedValue(undefined);
    refreshStatus.mockResolvedValue(undefined);

    render(<AuthSettingsCard />);

    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.change(screen.getByLabelText('Current admin password'), { target: { value: 'passwd6' } });
    fireEvent.click(screen.getByRole('button', { name: 'Disable authentication' }));

    await waitFor(() => {
      expect(updateSettings).toHaveBeenCalledWith(false, undefined, undefined, 'passwd6');
    });
    expect(refreshStatus).toHaveBeenCalled();
    expect(await screen.findByText('Authentication disabled')).toBeInTheDocument();
  });

  it('shows only current password when re-enabling with a retained password', () => {
    useAuthMock.mockReturnValue({
      authEnabled: false,
      setupState: 'password_retained',
      refreshStatus,
    });

    render(<AuthSettingsCard />);

    fireEvent.click(screen.getByRole('checkbox'));

    expect(screen.getByLabelText('Current admin password')).toBeInTheDocument();
    expect(screen.queryByLabelText('Set admin password')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Confirm new password')).not.toBeInTheDocument();
  });

  it('does not show new password fields while auth is already enabled', () => {
    useAuthMock.mockReturnValue({
      authEnabled: true,
      setupState: 'enabled',
      refreshStatus,
    });

    render(<AuthSettingsCard />);

    expect(screen.queryByLabelText('Set admin password')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Confirm new password')).not.toBeInTheDocument();
  });

  it('blocks initial enable when the new password is missing', async () => {
    render(<AuthSettingsCard />);

    fireEvent.click(screen.getByRole('checkbox'));
    fireEvent.click(screen.getByRole('button', { name: 'Enable authentication' }));

    expect(await screen.findByText('A new password is required')).toBeInTheDocument();
    expect(updateSettings).not.toHaveBeenCalled();
  });
});
