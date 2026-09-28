import React from 'react'
import CloseIcon from '@mui/icons-material/Close'

export default function AddRepoModal({
  isOpen,
  onClose,
  newRepoName,
  setNewRepoName,
  newRepoUrl,
  setNewRepoUrl,
  onSubmit,
  loading,
}) {
  if (!isOpen) return null

  return (
    <div className="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4">
      <div className="bg-surface border border-border rounded-2xl w-full max-w-md p-6 flex flex-col gap-4 shadow-2xl animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center justify-between pb-3 border-b border-border-soft">
          <h3 className="text-[16px] font-bold text-text m-0">Add Repository</h3>
          <button
            onClick={onClose}
            disabled={loading}
            className="text-text-dim hover:text-text cursor-pointer p-1 rounded-md transition-colors"
          >
            <CloseIcon sx={{ fontSize: 16 }} />
          </button>
        </div>

        <form
          onSubmit={(e) => {
            e.preventDefault()
            onSubmit()
          }}
          className="flex flex-col gap-3.5"
        >
          <div className="flex flex-col gap-1.5">
            <label className="font-mono text-[11px] text-text-mid uppercase tracking-wider">
              Repository Name
            </label>
            <input
              type="text"
              placeholder="e.g. MyProject"
              value={newRepoName}
              onChange={(e) => setNewRepoName(e.target.value)}
              disabled={loading}
              className="bg-bg border border-border rounded-lg px-3.5 py-2.5 text-[13.5px] text-text outline-none font-sans focus:border-accent-line transition-colors"
              required
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label className="font-mono text-[11px] text-text-mid uppercase tracking-wider">
              GitHub URL or Local Directory Path
            </label>
            <input
              type="text"
              placeholder="https://github.com/user/repo OR /path/to/repo"
              value={newRepoUrl}
              onChange={(e) => setNewRepoUrl(e.target.value)}
              disabled={loading}
              className="bg-bg border border-border rounded-lg px-3.5 py-2.5 text-[13.5px] text-text outline-none font-sans focus:border-accent-line transition-colors"
              required
            />
          </div>

          <div className="flex justify-end gap-2.5 mt-2 pt-3 border-t border-border-soft">
            <button
              type="button"
              onClick={onClose}
              disabled={loading}
              className="px-4 py-2 rounded-lg border border-border bg-transparent text-text-mid font-semibold text-[13px] cursor-pointer hover:bg-surface-2 hover:text-text transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={loading || !newRepoName.trim() || !newRepoUrl.trim()}
              className="px-5 py-2 rounded-lg bg-accent text-bg font-bold text-[13px] cursor-pointer hover:brightness-105 transition-all disabled:opacity-60 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {loading ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-bg border-t-transparent rounded-full animate-spin-custom" />
                  Indexing...
                </>
              ) : (
                'Add & Index Repo'
              )}
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}
