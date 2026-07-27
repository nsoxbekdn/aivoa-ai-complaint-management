import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { useAppDispatch, useAppSelector } from '../app/hooks';
import {
  fetchComplaints,
  setListOffset,
  setListSearch,
} from '../features/complaints/complaintsSlice';
import { labelFor } from '../features/complaints/labels';
import { ErrorAlert } from './ErrorAlert';
import { LoadingIndicator } from './LoadingIndicator';

export function ComplaintList() {
  const dispatch = useAppDispatch();
  const { items, total, limit, offset, search, loading, error } = useAppSelector(
    (state) => state.complaints.list,
  );
  const [searchInput, setSearchInput] = useState(search);

  useEffect(() => {
    dispatch(fetchComplaints({ limit, offset, search }));
  }, [dispatch, limit, offset, search]);

  const page = Math.floor(offset / limit) + 1;
  const pageCount = Math.max(1, Math.ceil(total / limit));

  return (
    <>
      <form
        className="toolbar"
        onSubmit={(event) => {
          event.preventDefault();
          dispatch(setListSearch(searchInput.trim()));
        }}
      >
        <input
          type="search"
          value={searchInput}
          placeholder="Search by complaint number, product, batch or customer"
          onChange={(event) => setSearchInput(event.target.value)}
        />
        <button type="submit" className="button button--primary" disabled={loading}>
          Search
        </button>
        {search && (
          <button
            type="button"
            className="button button--ghost"
            onClick={() => {
              setSearchInput('');
              dispatch(setListSearch(''));
            }}
          >
            Clear
          </button>
        )}
      </form>

      {error && <ErrorAlert title="Could not load complaints" message={error} />}

      <div className="card">
        {loading ? (
          <LoadingIndicator label="Loading complaints…" />
        ) : items.length === 0 ? (
          <div className="empty-state">
            <div className="empty-state__icon" aria-hidden="true">
              🗂
            </div>
            <div>{search ? 'No complaints match that search.' : 'No complaints saved yet.'}</div>
            <div className="text-small">
              <Link to="/">Log the first complaint →</Link>
            </div>
          </div>
        ) : (
          <>
            <div className="table-wrapper">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Number</th>
                    <th>Product</th>
                    <th>Batch</th>
                    <th>Type</th>
                    <th>Severity</th>
                    <th>AI risk</th>
                    <th>Status</th>
                    <th>Logged</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((complaint) => (
                    <tr key={complaint.id}>
                      <td>
                        <Link to={`/complaints/${complaint.id}`}>{complaint.complaint_number}</Link>
                      </td>
                      <td className="wrap">{complaint.product_name ?? '—'}</td>
                      <td>{complaint.batch_lot_number ?? '—'}</td>
                      <td>{labelFor(complaint.complaint_type)}</td>
                      <td>{labelFor(complaint.initial_severity)}</td>
                      <td>
                        <span className={`badge badge--${complaint.risk_level ?? 'unknown'}`}>
                          {complaint.risk_level ?? 'n/a'}
                        </span>
                      </td>
                      <td>{labelFor(complaint.status)}</td>
                      <td>{new Date(complaint.created_at).toLocaleDateString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="pagination">
              <span>
                {total} complaint{total === 1 ? '' : 's'} · page {page} of {pageCount}
              </span>
              <span style={{ display: 'flex', gap: 8 }}>
                {/* The buttons only move the offset; the effect above owns the fetching. */}
                <button
                  type="button"
                  className="button button--ghost"
                  disabled={offset === 0}
                  onClick={() => dispatch(setListOffset(offset - limit))}
                >
                  Previous
                </button>
                <button
                  type="button"
                  className="button button--ghost"
                  disabled={offset + limit >= total}
                  onClick={() => dispatch(setListOffset(offset + limit))}
                >
                  Next
                </button>
              </span>
            </div>
          </>
        )}
      </div>
    </>
  );
}
