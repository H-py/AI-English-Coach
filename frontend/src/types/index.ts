/** 通用类型集合 */

export type Maybe<T> = T | null

export interface SelectOption<T = string | number> {
  label: string
  value: T
  disabled?: boolean
}

/** 列表项通用标识 */
export interface WithId {
  id: string | number
}

export type ID = string | number
