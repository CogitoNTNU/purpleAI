import { useState } from "react";
import axiosInstance from "@/services/axios";
import { useAuth } from "@/services/AuthContext";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { MessageSquare } from "lucide-react";

interface Props {
  reviewId: number;
  businessOwnerId?: number;
  onReplyPosted: () => void;
}

export default function BusinessReply({ reviewId, businessOwnerId, onReplyPosted }: Props) {
  const { user } = useAuth();
  const [showForm, setShowForm] = useState(false);
  const [body, setBody] = useState("");
  const [loading, setLoading] = useState(false);

  const canReply = user && (user.role === "business_owner" && user.id === businessOwnerId);

  const handleSubmit = async () => {
    if (!body.trim()) return;
    setLoading(true);
    try {
      await axiosInstance.post("reviews/replies/", {
        review: reviewId,
        author: user?.id,
        body,
      });
      setBody("");
      setShowForm(false);
      onReplyPosted();
    } catch (e) {
      console.error("Failed to post reply:", e);
      alert("Failed to post reply");
    } finally {
      setLoading(false);
    }
  };

  if (!canReply) return null;

  return (
    <div className="mt-3">
      {!showForm ? (
        <Button
          variant="outline"
          size="sm"
          onClick={() => setShowForm(true)}
          className="flex gap-1"
        >
          <MessageSquare className="h-4 w-4" />
          Reply as Business
        </Button>
      ) : (
        <div className="space-y-2 border p-3 rounded-lg">
          <Textarea
            placeholder="Write your response..."
            value={body}
            onChange={(e) => setBody(e.target.value)}
            rows={3}
          />
          <div className="flex gap-2">
            <Button disabled={loading} onClick={handleSubmit} size="sm">
              {loading ? "Posting..." : "Post Reply"}
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setShowForm(false);
                setBody("");
              }}
              size="sm"
            >
              Cancel
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
