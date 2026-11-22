import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import InvestorGuidePage from '../InvestorGuidePage';

describe('InvestorGuidePage', () => {
  it('renders 30-second lessons and filters plain-Turkish glossary by keyword', () => {
    render(
      <MemoryRouter>
        <InvestorGuidePage />
      </MemoryRouter>,
    );

    expect(screen.getByText('30 Saniyelik Kartlarla Yatırımı Anla')).toBeInTheDocument();
    expect(screen.getByText('1. Bu Program Ne Yapar, Ne Yapmaz?')).toBeInTheDocument();

    const search = screen.getByLabelText('Sözlükte terim ara');
    fireEvent.change(search, { target: { value: 'TEFAS' } });

    expect(screen.getByText('TEFAS (Türkiye Fon Platformu)')).toBeInTheDocument();
    expect(screen.queryByText('VIX (Korku Endeksi)')).not.toBeInTheDocument();
  });
});
