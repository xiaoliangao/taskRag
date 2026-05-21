import { client } from "./client";

export interface AnnotationRect {
  x: number;
  y: number;
  w: number;
  h: number;
}

export type AnnotationKind = "highlight" | "comment" | "note";

export interface Annotation {
  id: number;
  document_id: number;
  topic_id: number;
  chunk_id: number | null;
  page_number: number;
  kind: AnnotationKind;
  color: string;
  selected_text: string;
  rects: AnnotationRect[];
  comment_md: string | null;
  note_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface AnnotationCreatePayload {
  page_number: number;
  kind: AnnotationKind;
  color?: string;
  selected_text: string;
  rects: AnnotationRect[];
  comment_md?: string | null;
  save_as_note?: boolean;
}

export interface AnnotationPatch {
  color?: string;
  kind?: AnnotationKind;
  comment_md?: string | null;
}

function base(topicId: number, documentId: number) {
  return `/topics/${topicId}/documents/${documentId}/annotations`;
}

export async function listAnnotations(topicId: number, documentId: number) {
  const { data } = await client.get<Annotation[]>(base(topicId, documentId));
  return data;
}

export async function createAnnotation(
  topicId: number,
  documentId: number,
  body: AnnotationCreatePayload,
) {
  const { data } = await client.post<Annotation>(base(topicId, documentId), body);
  return data;
}

export async function patchAnnotation(
  topicId: number,
  documentId: number,
  annotationId: number,
  body: AnnotationPatch,
) {
  const { data } = await client.patch<Annotation>(
    `${base(topicId, documentId)}/${annotationId}`,
    body,
  );
  return data;
}

export async function deleteAnnotation(
  topicId: number,
  documentId: number,
  annotationId: number,
) {
  await client.delete(`${base(topicId, documentId)}/${annotationId}`);
}
