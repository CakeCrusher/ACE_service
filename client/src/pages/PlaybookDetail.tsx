import { useQuery } from '@tanstack/react-query'
import { useParams, Link } from 'react-router-dom'
import { api } from '../api/client'

export default function PlaybookDetail() {
  const { playbookId } = useParams<{ playbookId: string }>()

  const { data: playbookData } = useQuery({
    queryKey: ['playbook', playbookId],
    queryFn: async () => {
      const response = await api.getPlaybook(playbookId!)
      return response.data
    },
    enabled: !!playbookId,
  })

  const { data: bulletsData } = useQuery({
    queryKey: ['bullets', playbookId],
    queryFn: async () => {
      const response = await api.getBullets(playbookId!)
      return response.data
    },
    enabled: !!playbookId,
  })

  if (!playbookId) {
    return <div>Invalid playbook ID</div>
  }

  return (
    <div className="px-4 sm:px-6 lg:px-8">
      <Link to="/" className="text-indigo-600 hover:text-indigo-900 text-sm mb-4 inline-block">
        ← Back to Playbooks
      </Link>

      <div className="mt-6">
        <h1 className="text-2xl font-semibold text-gray-900">
          {playbookData?.playbook.name || 'Unnamed Playbook'}
        </h1>
        <p className="mt-2 text-sm text-gray-700">
          ID: <span className="font-mono text-xs">{playbookData?.playbook.id}</span>
        </p>
        {playbookData?.playbook.description && (
          <p className="mt-2 text-sm text-gray-600">{playbookData.playbook.description}</p>
        )}
      </div>

      <div className="mt-8">
        <h2 className="text-xl font-semibold text-gray-900 mb-4">Bullets</h2>
        <div className="space-y-4">
          {bulletsData?.bullets.map((bullet) => (
            <div key={bullet.id} className="bg-white shadow rounded-lg p-4">
              <div className="flex justify-between items-start">
                <div className="flex-1">
                  <p className="text-sm text-gray-900">{bullet.content}</p>
                  <div className="mt-2 flex gap-4 text-xs text-gray-500">
                    <span>Helpful: {bullet.metadata.helpful_count}</span>
                    <span>Harmful: {bullet.metadata.harmful_count}</span>
                    <span>Neutral: {bullet.metadata.neutral_count}</span>
                  </div>
                </div>
                <span className="text-xs text-gray-400 font-mono ml-4">
                  {bullet.id.substring(0, 8)}...
                </span>
              </div>
            </div>
          ))}
          {bulletsData?.bullets.length === 0 && (
            <div className="text-center py-8 text-gray-500">
              No bullets found for this playbook.
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
