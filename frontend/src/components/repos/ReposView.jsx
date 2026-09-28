import React, { useState } from 'react'
import AddIcon from '@mui/icons-material/Add'
import SyncIcon from '@mui/icons-material/Sync'
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline'

import AddRepoModal from './AddRepoModal'
import UpdateOverlay from './UpdateOverlay'

export default function ReposView({
  reposList,
  onAddRepo,
  onUpdateRepo,
  onDeleteRepo,
  updatingRepoName,
  updateStep,
}) {
  const [showAddModal, setShowAddModal] = useState(false)
  const [newRepoName, setNewRepoName] = useState('')
  const [newRepoUrl, setNewRepoUrl] = useState('')
  const [addLoading, setAddLoading] = useState(false)

  const handleAddSubmit = async () => {
    setAddLoading(true)
    try {
      await onAddRepo(newRepoName, newRepoUrl)
      setNewRepoName('')
      setNewRepoUrl('')
      setShowAddModal(false)
    } finally {
      setAddLoading(false)
    }
  }

  return (
    <div className="flex flex-col gap-6">
      {/* UPDATE PROGRESS OVERLAY */}
      <UpdateOverlay
        isUpdating={!!updatingRepoName}
        targetRepo={updatingRepoName}
        step={updateStep}
      />

      {/* ADD REPO MODAL */}
      <AddRepoModal
        isOpen={showAddModal}
        onClose={() => setShowAddModal(false)}
        newRepoName={newRepoName}
        setNewRepoName={setNewRepoName}
        newRepoUrl={newRepoUrl}
        setNewRepoUrl={setNewRepoUrl}
        onSubmit={handleAddSubmit}
        loading={addLoading}
      />

      {/* REPOSITORIES CARD CONTAINER */}
      <div className="bg-surface border border-border rounded-xl p-6 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-[16px] font-bold text-text m-0">Configured Repositories</h3>
            <p className="font-mono text-[12px] text-text-dim m-0 mt-0.5">
              Codebases indexed into vector and BM25 hybrid search
            </p>
          </div>
          <button
            onClick={() => setShowAddModal(true)}
            className="flex items-center gap-1.5 bg-accent text-bg px-4 py-2 rounded-lg font-bold text-[13px] cursor-pointer hover:brightness-105 transition-all shadow-md"
          >
            <AddIcon sx={{ fontSize: 18 }} /> Add Repository
          </button>
        </div>

        {/* REPO ITEMS LIST */}
        <div className="flex flex-col gap-2.5">
          {reposList.length === 0 ? (
            <div className="py-6 text-center text-text-dim text-[13px]">
              No repositories configured yet. Click <b>Add Repository</b> to index your first codebase.
            </div>
          ) : (
            reposList.map((r, idx) => (
              <div
                key={idx}
                className="bg-surface-2 border border-border-soft rounded-lg p-3.5 px-4.5 flex items-center justify-between"
              >
                <div className="flex items-center gap-3">
                  <span
                    className="w-2.5 h-2.5 rounded-full flex-none"
                    style={{ backgroundColor: r.color }}
                  />
                  <div>
                    <div className="font-semibold text-[14px] text-text">{r.name}</div>
                    <div className="text-[11px] text-text-dim font-mono">
                      {r.count} chunks · Last synced: {r.last_synced || 'Just now'}
                    </div>
                  </div>
                </div>

                <div className="flex gap-2">
                  {/* UPDATE BUTTON */}
                  <button
                    onClick={() => onUpdateRepo(r.name)}
                    title={`Pull latest changes and re-index '${r.name}' only — other repos stay unchanged`}
                    className="flex items-center gap-1.25 bg-accent-soft border border-accent-line text-accent rounded-lg px-3.5 py-1.5 text-[12px] font-semibold cursor-pointer hover:bg-accent-line/30 transition-colors"
                  >
                    <SyncIcon sx={{ fontSize: 14 }} /> Update
                  </button>

                  {/* DELETE BUTTON */}
                  <button
                    onClick={() => onDeleteRepo(r.name)}
                    className="flex items-center gap-1.25 bg-red-500/10 border border-red-500/30 text-red-400 rounded-lg px-3.5 py-1.5 text-[12px] font-semibold cursor-pointer hover:bg-red-500/20 transition-colors"
                  >
                    <DeleteOutlineIcon sx={{ fontSize: 14 }} /> Delete
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      </div>

      {/* VECTOR INDEX STATUS OVERVIEW */}
      <div className="bg-surface border border-border rounded-xl p-6">
        <h3 className="m-0 mb-3 text-[15px] font-bold text-text">Vector Index Status</h3>
        <div className="grid grid-cols-[repeat(auto-fit,minmax(200px,1fr))] gap-3">
          {['code.faiss', 'commits.faiss', 'readme.faiss', 'bm25_code.pkl'].map((name) => (
            <div
              key={name}
              className="font-mono text-[11.5px] text-text-mid bg-surface-2 border border-border-soft p-3 rounded-lg flex items-center justify-between"
            >
              <span className="text-text font-medium">{name}</span>
              <span className="text-[#7FD8A6] font-semibold">Active</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}
