export interface ApiErrorBody {
  error: {
    message: string
    fields?: { location: string }[]
  }
}

export interface PageRequest {
  limit: number
  cursor?: string | null
}

export interface Page<T> {
  items: T[]
  next_cursor: string | null
}
