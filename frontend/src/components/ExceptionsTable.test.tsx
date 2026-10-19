import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import ExceptionsTable from './ExceptionsTable';

describe('ExceptionsTable', () => {
  it('shows a friendly empty state', () => {
    render(<ExceptionsTable rows={[]} />);
    expect(screen.getByText(/no exceptions/i)).toBeInTheDocument();
  });

  it('renders exception rows with their columns', () => {
    render(
      <ExceptionsTable
        rows={[
          { TXN_ID: 'T1', REASON: 'timeout' },
          { TXN_ID: 'T2', REASON: 'invalid_token' },
        ]}
      />,
    );

    expect(screen.getByTestId('exceptions-table')).toBeInTheDocument();
    expect(screen.getByText('T1')).toBeInTheDocument();
    expect(screen.getByText('invalid_token')).toBeInTheDocument();
    expect(screen.getByText('(2)')).toBeInTheDocument();
  });
});
