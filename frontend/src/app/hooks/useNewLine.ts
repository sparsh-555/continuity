import { useCallback, useState } from 'react'
import { useNavigate } from 'react-router'

import { createLine } from '../lib/api'

export function useNewLine() {
  const navigate = useNavigate()
  const [creating, setCreating] = useState(false)

  const createNewLine = useCallback(async () => {
    if (creating) {
      return
    }

    setCreating(true)
    try {
      const created = await createLine('Untitled board')
      navigate(`/design/${created.id}`)
    } finally {
      setCreating(false)
    }
  }, [creating, navigate])

  return { createNewLine, creating }
}
